#!/usr/bin/env python3
"""Avisa o Bing (e demais buscadores IndexNow) sobre as URLs publicadas."""
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests

raiz = Path(__file__).resolve().parent.parent
base = os.environ["SITE_BASE_URL"].rstrip("/")
chave = json.loads((raiz / "fontes.json").read_text(encoding="utf-8"))["indexnow_key"]
urls = (raiz / "_site" / "urls.txt").read_text().split()

for i in range(0, len(urls), 10000):
    r = requests.post(
        "https://api.indexnow.org/indexnow",
        json={"host": urlparse(base).netloc, "key": chave,
              "keyLocation": f"{base}/{chave}.txt", "urlList": urls[i:i + 10000]},
        timeout=60,
    )
    print(f"IndexNow: {len(urls[i:i + 10000])} URLs -> HTTP {r.status_code} {r.text[:200]}")
    if r.status_code not in (200, 202):
        sys.exit(1)
