# EMPYREANS – Wuxia Archiv für GitHub Pages

Eine automatisch aktualisierte Startseite für alle HTML- und Markdown-Seiten in einem Repository. Mit Wuxia-Design, eigener Panorama-Grafik, Suchfunktion, Kategorien, Änderungsdaten und AES-256-GCM-verschlüsseltem Katalog.

**Wichtig:** Die PIN schützt die **Startseite/Seitenübersicht**, **nicht die einzelnen Seiten**. Wer die URL einer Unterseite kennt, kann sie bei GitHub Pages direkt öffnen. Für tatsächlichen Zugriffsschutz auf sämtliche Unterseiten ist ein externer Authentifizierungsdienst nötig (zum Beispiel Cloudflare Access vor einer eigenen Domain). Bei einem öffentlichen GitHub-Repository sind die Dateien zudem öffentlich einsehbar. Die PIN ist keine GitHub-Anmeldung.

## Installation in 5 Schritten

1. Die ZIP-Datei entpacken und **den Inhalt** des Ordners `empyreans-wuxia-portal/` ins **Hauptverzeichnis des gewünschten GitHub-Repositories** hochladen. Bestehende Seiten, Assets und Ordner bleiben erhalten. Bei einer vorhandenen `.github/workflows/pages.yml` zuerst diese Workflow-Datei prüfen, damit kein anderer Deploy-Workflow in Konflikt gerät.
2. Auf GitHub im Repository `Settings → Secrets and variables → Actions → New repository secret` öffnen. Secret-Name: **`PORTAL_PIN`**. Als Wert eine selbst gewählte PIN eintragen. **Mindestens 6 Zeichen**, für besseren Schutz **mindestens 8 zufällige Ziffern oder ein längeres Passwort**. Niemals die PIN in eine Datei committen.
3. Unter `Settings → Pages → Build and deployment` bei **Source: GitHub Actions** wählen.
4. Dateien nach `main` committen/pushen. Verwendet das Repository `master` oder einen anderen Branch, in `.github/workflows/pages.yml` unter `on.push.branches` entsprechend anpassen.
5. Unter `Actions → EMPYREANS · Wuxia Archiv veröffentlichen` auf die erfolgreiche Veröffentlichung warten. Die Website ist anschließend unter der GitHub-Pages-Adresse des Repositories verfügbar. Für die Nutzung per Browser ist HTTPS erforderlich.

Bei bereits laufenden Pages-Workflows: Nicht zwei konkurrierende Deployments verwenden. Das hier gelieferte Workflow-Schema ersetzt oder integriert den bestehenden Publish-Schritt.

## Was passiert bei neuen Seiten?

Bei **jedem Push auf `main`** startet GitHub Actions und:

1. Erfasst `.html`, `.htm`, `.md` und `.markdown` in allen Unterordnern (soweit nicht ausgeschlossen).
2. Liest HTML-Titel aus `<title>`, alternativ `<h1>`; Beschreibungen aus `<meta name="description">`, `og:description` oder dem ersten Absatz. Bei Markdown werden YAML-Frontmatter (`title`, `description`, `tags`, `image`) und Überschriften/Absätze verwendet.
3. Ermittelt das Änderungsdatum aus Git. Kategorien entsprechen standardmäßig dem ersten Ordner (z. B. `gvg/`, `builds/`, `guides/`), Root-Seiten erhalten `Hauptarchiv`.
4. Kopiert vorhandene HTML-Seiten und deren übliche Web-Assets ins Deployment, wandelt Markdown in lesbare HTML-Seiten um und erstellt den verschlüsselten Katalog mit neuen zufälligen Salt/IV-Werten.
5. Veröffentlicht die neue Startseite mit Suche, Ordnerfiltern und Sortierung.

**Bestehende `index.html`:** Eine vorhandene Startseite im Root wird automatisch als `startseite-original.html` veröffentlicht und im Archiv gelistet. Hat dieser Name bereits eine Seite, erhält die kopierte Startseite einen fortlaufenden Zusatz. Unterseiten wie `guides/index.html` bleiben unverändert. Die neue Portal-Startseite ersetzt ausschließlich den Einstieg `/index.html` des veröffentlichten Deployments – **nicht** die Originaldatei im Repository.

## Beschreibungen automatisch und optional redaktionell

Für bestehende HTML-Seiten empfehlen sich aussagekräftige Metadaten:

```html
<title>EMPYREANS – GvG Defense Guide</title>
<meta name="description" content="Tower-Rollen, Rotationen und Verteidigung im Gildenkrieg.">
<meta property="og:image" content="./bilder/gvg-cover.webp">
```

Markdown:

```markdown
---
title: Tank-Handbuch
description: Best-in-Slot, Rotationen und Strategien für PvE und GvG.
tags: [Tank, Thundercry, Build]
image: ./cover.webp
---
# Tank-Handbuch
...
```

Im optionalen `.portal/metadata.json` lassen sich Kategorien, Titel, Bilder, Tags und Hervorhebungen einzelner Dateien überschreiben. Schlüssel ist der **Quellpfad im Repository**, z. B. `gvg/defense.html`:

```json
{
  "gvg/defense.html": {
    "category": "Gildenkrieg",
    "tags": ["GvG", "Defense"],
    "featured": true
  },
  "intern/entwurf.html": { "hidden": true }
}
```

`hidden: true` blendet die Seite **nur im Archiv** aus, sie wird trotzdem veröffentlicht und bleibt direkt aufrufbar. Soll eine Datei nicht veröffentlicht werden, muss sie aus dem Web-Quellpfad entfernt oder in der Ausschlussliste in `.portal/config.json` erfasst werden.

Die in der beiliegenden `metadata.json` verwendete Beispieladresse `beispiele/gvg-defense.html` ist nur eine Vorlage und erzeugt **keine** Beispielseite.

## Branding anpassen

- `.portal/config.json`: Name, Untertitel, Einleitung, Markdown-Aktivierung, ausgeschlossene Dateien.
- `.portal/assets/wuxia-landscape.webp`: die eigene Wuxia-Hintergrundgrafik.
- `.portal/assets/portal.css`: Farben, Layout, responsive Darstellung.
- `.portal/assets/sigil.svg`: Gildensiegel.
- `.portal/metadata.json`: individuelle Metadaten.

Die Startseite speichert weder die PIN noch den entschlüsselten Katalog in `localStorage`. Nach einem Neuladen muss die PIN erneut eingegeben werden. Der Katalog wird mit **PBKDF2-HMAC-SHA-256 (650.000 Iterationen)** zu einem AES-256-GCM-Schlüssel entschlüsselt. Ein kurzer numerischer PIN kann bei Zugriff auf die verschlüsselte Datei offline durchprobiert werden – deshalb ist eine längere PIN wichtig. Der GitHub-Secret-Wert wird im Build über die Umgebungsvariable gelesen und niemals in die Website eingebettet. **Keine absolute Sicherheit bei rein statischem Hosting.**

## Lokal testen

Python 3.12+ installieren und aus dem Repository-Root starten:

```bash
python -m pip install -r requirements.txt
# Hier nur für einen lokalen Test – nicht committen:
PORTAL_PIN='nur-eine-test-pin-123' python tools/build_portal.py --source . --output _site
python -m http.server 8000 --directory _site
```

Unter Windows PowerShell:

```powershell
python -m pip install -r requirements.txt
$env:PORTAL_PIN='nur-eine-test-pin-123'
python tools/build_portal.py --source . --output _site
python -m http.server 8000 --directory _site
```

Im Browser `http://localhost:8000` öffnen; `localhost` gilt für WebCrypto als sicherer Kontext. Der Ausgabeordner `_site/` ist generiert und gehört nicht ins Repository.

## Hinweise zu Grenzen und Kompatibilität

- Die Startseite wird **bei jedem Push** neu erzeugt, nicht sekündlich zur Laufzeit. Das ist die zuverlässige serverlose Arbeitsweise auf GitHub Pages.
- Seiten in separaten Frameworks (React, Next.js usw.) müssen ggf. vorher gebaut werden. Der Builder verarbeitet vorhandene HTML-Dateien und einfache Markdown-Seiten, führt aber kein `npm build` aus.
- Der Builder veröffentlicht nur bekannte **Web-Dateiendungen** und niemals `.git`, `.github`, `.portal`, `tools`, `tests`, `node_modules`, `.env` oder beliebige Quell-/Secret-Dateien. **Trotzdem** darf ein GitHub-Pages-Repository keine vertraulichen Webdaten enthalten.
- Bei einem Root-`index.html` kann dessen Linkverhalten abweichen, wenn es absolute URLs oder ein festes Routing zum Site-Root voraussetzt.
- Einträge mit `meta og:image` werden nur dann als Cover eingebaut, wenn die Bilddatei innerhalb der Website lokal existiert. Externe Bilder werden für das Portal bewusst nicht eingebunden.
- Interne Markdown-Links auf `.md` ggf. als `.html` schreiben, wenn sie in der veröffentlichten Darstellung auf andere konvertierte Seiten verweisen.
- Das `CNAME`-File einer bestehenden Custom Domain wird übernommen. Bei bereits konfigurierten GitHub-Pages-Repositories muss die Pages-Source auf **GitHub Actions** umgestellt werden.

**Offizielle GitHub-Dokumentation:** https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages
