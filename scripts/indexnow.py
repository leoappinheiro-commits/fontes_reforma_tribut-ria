#!/usr/bin/env python3
"""Avisa o Bing (IndexNow) sobre as URLs publicadas. Nunca derruba o workflow."""
import json
import os
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

raiz = Path(__file__).resolve().parent.parent
base = os.environ["SITE_BASE_URL"].rstrip("/")
chave = json.loads((raiz / "fontes.json").read_text(encoding="utf-8"))["indexnow_key"]
urls = (raiz / "_site" / "urls.txt").read_text().split()
key_url = f"{base}/{chave}.txt"


def anotar(nivel, msg):
    print(f"::{nivel} title=IndexNow::{msg}")


# espera a chave ficar acessível no Pages (propagação pode levar alguns minutos)
for tentativa in range(10):
    try:
        r = requests.get(key_url, timeout=30)
        if r.status_code == 200 and r.text.strip() == chave:
            break
    except requests.RequestException:
        pass
    time.sleep(30)
else:
    anotar("warning", f"chave não acessível em {key_url}; IndexNow não enviado")
    raise SystemExit(0)

for i in range(0, len(urls), 10000):
    lote = urls[i:i + 10000]
    r = requests.post(
        "https://api.indexnow.org/indexnow",
        json={"host": urlparse(base).netloc, "key": chave, "keyLocation": key_url, "urlList": lote},
        timeout=60,
    )
    nivel = "notice" if r.status_code in (200, 202) else "warning"
    anotar(nivel, f"{len(lote)} URLs -> HTTP {r.status_code} {r.text[:300]}")
