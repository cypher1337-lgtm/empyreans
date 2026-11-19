"""Self-contained smoke test. Run: python -m unittest discover -s tests -v"""
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from importlib.machinery import SourceFileLoader

BASE = Path(__file__).resolve().parents[1]
loader = SourceFileLoader("portal_builder", str(BASE / "tools" / "build_portal.py"))
builder = loader.load_module()

class BuildTest(unittest.TestCase):
    def test_encrypt_and_extract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "source"; root.mkdir()
            shutil.copytree(BASE / ".portal", root / ".portal")
            (root / "index.html").write_text('<title>Alte Startseite</title><meta name="description" content="Original vom Repository">', encoding="utf-8")
            gvg = root / "gvg";gvg.mkdir()
            (gvg / "defense.html").write_text('<title>Defense für GvG</title><meta name="description" content="Alle Tower Rollen">', encoding="utf-8")
            (gvg / "guide.md").write_text('---\ntitle: GvG Planer\ndescription: Beste Formation\ntags: [Tank, Healer]\n---\n# GvG Planer\n\nMehr Text.', encoding="utf-8")
            (root / ".env").write_text('PRIVATE_DO_NOT_PUBLISH', encoding="utf-8")
            pin = '73519482'
            out = root / "_site"
            pages = builder.build(root,out,pin,verbose=False)
            self.assertEqual(len(pages), 3)
            self.assertTrue((out / 'startseite-original.html').exists())
            self.assertTrue((out / 'gvg/guide.html').exists())
            self.assertTrue((out / 'index.html').exists())
            self.assertFalse((out / '.env').exists())
            self.assertFalse((out / '.portal').exists())
            self.assertFalse((out / 'README.md').exists())
            self.assertNotIn(pin, (out / '_empyreans/catalog.enc.json').read_text())
            content = json.loads((out / '_empyreans/catalog.enc.json').read_text())
            b64 = lambda value: base64.b64decode(value)
            key = hashlib.pbkdf2_hmac('sha256',pin.encode(),b64(content['salt']),content['iterations'],dklen=32)
            decrypted = AESGCM(key).decrypt(b64(content['iv']),b64(content['data']),builder.AAD)
            catalog = json.loads(decrypted)
            self.assertEqual(len(catalog['pages']),3)
            self.assertIn('gvg/guide.html',[p['path'] for p in catalog['pages']])
            self.assertIn('startseite-original.html',[p['path'] for p in catalog['pages']])
            with self.assertRaises(Exception):
                wrong = hashlib.pbkdf2_hmac('sha256',b'111111',b64(content['salt']),content['iterations'],dklen=32)
                AESGCM(wrong).decrypt(b64(content['iv']),b64(content['data']),builder.AAD)

if __name__ == '__main__':unittest.main()
