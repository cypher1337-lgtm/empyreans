#!/usr/bin/env python3
"""Build a self-updating, PIN-encrypted GitHub Pages directory from a repo.

Only the DIRECTORY is encrypted. Pages themselves remain public on GitHub Pages.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
from html import escape
from html.parser import HTMLParser
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
from urllib.parse import quote, urlsplit, unquote
import hashlib
import secrets
import fnmatch

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import mistune
import yaml

AAD = b"EMPYREANS-PORTAL-v1"
KDF_ITERATIONS = 650_000
ALLOWED_ASSETS = {
    ".html", ".htm", ".css", ".js", ".mjs", ".json", ".svg", ".png",
    ".jpg", ".jpeg", ".webp", ".gif", ".ico", ".pdf", ".webmanifest",
    ".mp4", ".webm", ".ogg", ".mp3", ".wav", ".woff", ".woff2",
    ".ttf", ".otf", ".wasm", ".txt", ".xml", ".avif", ".map",
}
IGNORED_FOLDERS = {".git", ".github", ".portal", "tools", "tests", "node_modules", "__pycache__", ".venv", "venv", "_site", "dist", "build", ".idea", ".vscode"}
MD_RENDERER = mistune.create_markdown(escape=True, plugins=["table", "strikethrough", "task_lists", "url"])


class PageHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.heading = ""
        self.description = ""
        self.og_description = ""
        self.image = ""
        self.first_image = ""
        self.paragraph = ""
        self._in_title = False
        self._in_h1 = False
        self._in_p = False
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("script", "style", "noscript", "svg", "template"):
            self._skip += 1
        if self._skip:
            return
        if tag == "title": self._in_title = True
        if tag == "h1": self._in_h1 = True
        if tag == "p" and not self.paragraph: self._in_p = True
        if tag == "img" and not self.first_image:
            candidate = (a.get("src") or "").strip()
            if candidate and not re.search(r"(favicon|logo|icon|sprite|avatar)", candidate, re.I):
                self.first_image = candidate
        if tag == "meta":
            kind = (a.get("name") or a.get("property") or "").lower()
            content = (a.get("content") or "").strip()
            if kind == "description" and not self.description: self.description = content
            if kind == "og:description" and not self.og_description: self.og_description = content
            if kind in ("og:image", "twitter:image") and not self.image: self.image = content

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg", "template") and self._skip:
            self._skip -= 1
        if tag == "title": self._in_title = False
        if tag == "h1": self._in_h1 = False
        if tag == "p": self._in_p = False

    def handle_data(self, data):
        if self._skip: return
        value = data.strip()
        if not value: return
        if self._in_title: self.title += " " + value
        if self._in_h1 and len(self.heading) < 300: self.heading += " " + value
        if self._in_p and len(self.paragraph) < 500: self.paragraph += " " + value


def clean(s, limit=190):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if len(s) <= limit else s[:limit-1].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"


def path_url(path):
    return "/".join(quote(part, safe="-._~") for part in PurePosixPath(path).parts)


def read_md(path):
    raw = path.read_text(encoding="utf-8-sig", errors="replace")
    meta = {}
    if raw.startswith("---\n"):
        parts = raw.split("\n---\n", 1)
        if len(parts) == 2:
            data = yaml.safe_load(parts[0][4:]) or {}
            if isinstance(data, dict):
                meta = data
                raw = parts[1]
    return raw, meta


def md_meta(markdown, meta):
    title = meta.get("title") or ""
    if not title:
        m = re.search(r"^#\s+(.+)$", markdown, re.M)
        if m: title = m.group(1).strip("* _`")
    summary = meta.get("description") or meta.get("summary") or ""
    if not summary:
        body = re.sub(r"```[\s\S]*?```", "", markdown)
        for paragraph in re.split(r"\n\s*\n", body):
            paragraph = paragraph.strip()
            if not paragraph or paragraph.startswith(("#", "!", "|", "- ", "* ", ">", "---")):
                continue
            summary = re.sub(r"!?\[([^\]]+)\]\([^)]*\)", r"\1", paragraph)
            summary = re.sub(r"[*_`~]", "", summary)
            break
    return title, summary


def pretty_category(folder):
    special = {"gvg": "GvG", "pvp": "PvP", "pve": "PvE", "faq": "FAQ", "dps": "DPS"}
    normalized = folder.replace("-", " ").replace("_", " ")
    return special.get(normalized.lower(), normalized.title())


def valid_image(image, source_rel, source_root, output_root):
    if not isinstance(image, str): return ""
    image = image.strip()
    if not image or image.startswith(("//", "data:")): return ""
    parsed = urlsplit(image)
    if parsed.scheme or parsed.netloc: return ""  # No third-party images/tracking in index.
    rel = unquote(parsed.path)
    if not rel: return ""
    if rel.startswith("/"):
        candidate = PurePosixPath(rel.lstrip("/"))
    else:
        candidate = PurePosixPath(source_rel).parent / rel
    normalized = os.path.normpath(str(candidate)).replace("\\", "/")
    if normalized.startswith("../") or normalized == ".." or normalized.startswith("/"):
        return ""
    if (output_root / normalized).is_file():
        return path_url(normalized)
    if (source_root / normalized).is_file():
        return path_url(normalized)
    return ""


def updated_at(root, rel):
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%cI", "--", str(rel)], cwd=root,
            capture_output=True, text=True, timeout=6, check=False
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return datetime.fromtimestamp((root / rel).stat().st_mtime, timezone.utc).isoformat()


def excluded(rel, patterns):
    path = str(rel).replace("\\", "/")
    if any(folder in IGNORED_FOLDERS for folder in rel.parts[:-1]): return True
    if any(p.startswith(".") and p != ".well-known" for p in rel.parts): return True
    return any(fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(rel.name, pattern) for pattern in patterns)


def markdown_page_html(body, title, back, theme_root):
    rendered = MD_RENDERER(body)
    return f'''<!doctype html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)}</title><link rel="stylesheet" href="{theme_root}_empyreans/reader.css"></head>
<body><div class="page"><a class="home" href="{back}">← Zurück zum Wuxia-Archiv</a>
<div class="red-line"></div><article class="markdown-body">{rendered}</article>
<footer>EMPYREANS · WUXIA ARCHIV</footer></div></body></html>'''


def build(root: Path, output: Path, pin: str, verbose=True):
    root = root.resolve()
    output = output.resolve()
    if not pin or len(pin) < 6:
        raise ValueError("PORTAL_PIN fehlt oder hat weniger als 6 Zeichen. Empfehlung: mindestens 8 Ziffern.")
    if output == root or root in output.parents and output.name != "_site":
        raise ValueError("Unzulässiger Ausgabeordner; _site ist empfohlen.")
    portal = root / ".portal"
    if not portal.is_dir(): raise FileNotFoundError(".portal/ fehlt. Dateien in das Repository-Root kopieren.")
    config = json.loads((portal / "config.json").read_text(encoding="utf-8"))
    overrides_path = portal / "metadata.json"
    overrides = json.loads(overrides_path.read_text(encoding="utf-8")) if overrides_path.exists() else {}
    patterns = config.get("exclude", [])
    if output.exists(): shutil.rmtree(output)
    output.mkdir(parents=True)
    (output / ".nojekyll").touch()

    all_files = [p for p in root.rglob("*") if p.is_file() and not p.is_symlink() and not excluded(p.relative_to(root), patterns) and p != output]
    pages = []
    existing = {p.relative_to(root).as_posix() for p in all_files}
    original_index_dest = "startseite-original.html"
    suffix = 2
    while original_index_dest in existing:
        original_index_dest = f"startseite-original-{suffix}.html"
        suffix += 1
    # Copy static web assets without publishing source files, private config or .github secrets.
    for file in all_files:
        rel = file.relative_to(root)
        suffix = file.suffix.lower()
        if suffix not in ALLOWED_ASSETS and rel.as_posix() != "CNAME":
            continue
        dest = output / (original_index_dest if rel.as_posix() == "index.html" else rel.as_posix())
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file, dest)

    md_candidates = [p for p in all_files if p.suffix.lower() in {".md", ".markdown"}] if config.get("scanMarkdown", True) else []
    html_candidates = [p for p in all_files if p.suffix.lower() in {".html", ".htm"}]
    occupied = {p.relative_to(output).as_posix() for p in output.rglob("*") if p.is_file()}

    for file in html_candidates + md_candidates:
        rel = file.relative_to(root)
        source_rel = rel.as_posix()
        is_md = file.suffix.lower() in {".md", ".markdown"}
        if is_md:
            target_rel = rel.with_suffix(".html").as_posix()
            if target_rel in occupied:
                if verbose: print(f"Übersprungen (HTML hat Vorrang): {source_rel} -> {target_rel}")
                continue
            raw, fm = read_md(file)
            title, description = md_meta(raw, fm)
            parent_depth = len(PurePosixPath(target_rel).parts) - 1
            theme_root = "../" * parent_depth
            html_text = markdown_page_html(raw, clean(title, 150) or file.stem, theme_root, theme_root)
            dest = output / target_rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(html_text, encoding="utf-8")
            occupied.add(target_rel)
            image = fm.get("image") or fm.get("cover") or ""
            front_tags = fm.get("tags") or []
        else:
            parser = PageHTMLParser()
            html_source = file.read_text(encoding="utf-8-sig", errors="replace")
            parser.feed(html_source)
            title = parser.title or parser.heading
            description = parser.description or parser.og_description or parser.paragraph
            image = parser.image or parser.first_image
            front_tags = []
            target_rel = original_index_dest if source_rel == "index.html" else source_rel
        fields = overrides.get(source_rel, {})
        if not isinstance(fields, dict): fields = {}
        if fields.get("hidden") is True: continue
        title = clean(fields.get("title") or title or file.stem.replace("-", " ").replace("_", " "), 100)
        description = clean(fields.get("description") or description or f"Eine Seite aus dem EMPYREANS-Archiv: {title}", 210)
        category = clean(fields.get("category") or (pretty_category(rel.parts[0]) if len(rel.parts) > 1 else "Hauptarchiv"), 60)
        tags = fields.get("tags", front_tags)
        if isinstance(tags, str): tags = [t.strip() for t in tags.split(",")]
        if not isinstance(tags, list): tags = []
        tags = [clean(t, 30) for t in tags if t][:6]
        image_url = valid_image(fields.get("image") or image, source_rel, root, output)
        pages.append({
            "title": title, "description": description, "category": category,
            "path": path_url(target_rel), "tags": tags, "image": image_url,
            "updated": updated_at(root, rel), "featured": bool(fields.get("featured", False)),
            "kind": "markdown" if is_md else "html"
        })

    pages.sort(key=lambda item: item["updated"], reverse=True)
    generated = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    payload = json.dumps({"pages": pages, "builtAt": generated}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    salt = secrets.token_bytes(16)
    iv = secrets.token_bytes(12)
    key = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, KDF_ITERATIONS, dklen=32)
    ciphertext = AESGCM(key).encrypt(iv, payload, AAD)
    blob = {
        "format": "EMPYREANS-PORTAL-v1", "iterations": KDF_ITERATIONS,
        "salt": base64.b64encode(salt).decode(), "iv": base64.b64encode(iv).decode(),
        "data": base64.b64encode(ciphertext).decode()
    }
    artdir = output / "_empyreans"
    artdir.mkdir()
    (artdir / "catalog.enc.json").write_text(json.dumps(blob, separators=(",", ":")), encoding="utf-8")
    for file in (portal / "assets").iterdir():
        if file.is_file(): shutil.copy2(file, artdir / file.name)
    template = (portal / "templates" / "index.html").read_text(encoding="utf-8")
    replacements = {
        "%%SITE_TITLE%%": escape(config.get("siteTitle", "EMPYREANS · WUXIA ARCHIV")),
        "%%SITE_SUBTITLE%%": escape(config.get("siteSubtitle", "Wissen. Strategie. Legenden.")),
        "%%SITE_INTRO%%": escape(config.get("siteIntro", "Alle Werke, Guides und Strategien an einem Ort.")),
    }
    for key2, value in replacements.items(): template = template.replace(key2, value)
    (output / "index.html").write_text(template, encoding="utf-8")
    if verbose:
        print(f"{len(pages)} Seiten katalogisiert. PIN wurde nicht gespeichert. Ausgabe: {output}")
        print(f"Alte Root-Startseite: {original_index_dest if 'index.html' in existing else '(nicht vorhanden)'}")
    return pages


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=".")
    parser.add_argument("--output", default="_site")
    args = parser.parse_args()
    try:
        build(Path(args.source), Path(args.output), os.environ.get("PORTAL_PIN", ""))
    except (ValueError, FileNotFoundError) as exc:
        parser.exit(2, f"Fehler: {exc}\n")
