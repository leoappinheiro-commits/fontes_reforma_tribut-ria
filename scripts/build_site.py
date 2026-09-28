#!/usr/bin/env python3
"""
Gera um site estático com a legislação da reforma tributária fatiada por
artigo (uma página por artigo/anexo), para uso como fonte de conhecimento
de agentes que buscam via Bing (Copilot).

Uso:
    SITE_BASE_URL=https://usuario.github.io/repo python scripts/build_site.py

Saída: pasta _site/ (HTML + sitemap.xml + robots.txt + chave IndexNow).
"""
from __future__ import annotations

import datetime as dt
import html
import json
import os
import re
import sys
import unicodedata
from pathlib import Path

import requests
from bs4 import BeautifulSoup

RAIZ = Path(__file__).resolve().parent.parent
SAIDA = RAIZ / "_site"
MAX_CHARS = 12000          # páginas maiores que isso são divididas em partes
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
HOJE = dt.date.today()

avisos: list[str] = []


GHA = os.environ.get("GITHUB_ACTIONS") == "true"


def aviso(msg: str) -> None:
    avisos.append(msg)
    print(f"[AVISO] {msg}", file=sys.stderr)
    if GHA:
        print(f"::warning title=Aviso do build::{msg}")


def nota(titulo: str, msg: str) -> None:
    """Publica um resumo como anotação do GitHub Actions (legível pela API)."""
    if GHA:
        msg = msg.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        print(f"::notice title={titulo}::{msg}")


# --------------------------------------------------------------------------
# Download
# --------------------------------------------------------------------------
def obter_bytes(fonte: dict) -> bytes | None:
    manual = RAIZ / fonte.get("arquivo_manual", "")
    if fonte.get("arquivo_manual") and manual.is_file():
        print(f"[{fonte['id']}] usando arquivo manual {manual.name}")
        return manual.read_bytes()
    url = fonte.get("url")
    if not url:
        aviso(f"{fonte['id']}: sem URL e sem arquivo manual; fonte ignorada")
        return None
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=120)
        r.raise_for_status()
        print(f"[{fonte['id']}] baixado {len(r.content):,} bytes de {url}")
        return r.content
    except Exception as e:  # noqa: BLE001
        aviso(f"{fonte['id']}: falha ao baixar {url} ({e}); "
              f"salve o arquivo em {fonte.get('arquivo_manual')}")
        return None


# --------------------------------------------------------------------------
# Extração de parágrafos
# --------------------------------------------------------------------------
def limpar(txt: str) -> str:
    txt = txt.replace("\xa0", " ")
    return re.sub(r"\s+", " ", txt).strip()


def decodificar(raw: bytes) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def paragrafos_planalto(raw: bytes) -> list[str]:
    """Extrai parágrafos do HTML do Planalto, SEM o texto tachado
    (redações revogadas/alteradas, que o Planalto mantém riscadas)."""
    soup = BeautifulSoup(decodificar(raw), "lxml")
    for tag in soup.find_all(["strike", "s", "del", "script", "style"]):
        tag.decompose()
    # o Planalto também risca via CSS em alguns textos
    for tag in soup.find_all(style=re.compile(r"line-through", re.I)):
        tag.decompose()

    saida: list[str] = []
    for el in soup.find_all(["p", "tr"]):
        if el.name == "p" and el.find_parent("tr") is not None:
            continue  # conteúdo de tabela é tratado por linha
        if el.name == "tr":
            celulas = [limpar(td.get_text(" ")) for td in el.find_all(["td", "th"])]
            txt = " | ".join(c for c in celulas if c)
        else:
            txt = limpar(el.get_text(" "))
        if txt:
            saida.append(txt)
    return saida


INICIO_BLOCO = re.compile(
    r"^(Art\.\s*\d|§\s*\d|Parágrafo único|[IVXLCDM]+\s*[-–]\s|[a-z]\)\s|"
    r"LIVRO\s|TÍTULO\s|CAPÍTULO\s|Seção\s|SEÇÃO\s|Subseção\s|SUBSEÇÃO\s|ANEXO\s)"
)


def linhas_pdf(raw: bytes) -> list[str]:
    import io
    import pdfplumber

    paginas: list[list[str]] = []
    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        for pg in pdf.pages:
            t = pg.extract_text() or ""
            paginas.append([limpar(l) for l in t.splitlines() if limpar(l)])

    # remove cabeçalhos/rodapés que se repetem em mais da metade das páginas
    from collections import Counter
    cont = Counter(l for pg in paginas for l in set(pg))
    n = max(len(paginas), 1)
    repetidas = {l for l, c in cont.items() if n >= 4 and c > n / 2}
    linhas = [l for pg in paginas for l in pg if l not in repetidas
              and not re.fullmatch(r"(p[áa]g(ina)?\.?\s*)?\d+(\s*(de|/)\s*\d+)?", l, re.I)]
    return linhas


def paragrafos_pdf(raw: bytes) -> list[str]:
    paras: list[str] = []
    for l in linhas_pdf(raw):
        if not paras or INICIO_BLOCO.match(l):
            paras.append(l)
        elif paras[-1].endswith("-") and not paras[-1].endswith(" -"):
            paras[-1] = paras[-1][:-1] + l
        else:
            paras[-1] += " " + l
    return paras


# --------------------------------------------------------------------------
# Segmentação em unidades (artigos, anexos)
# --------------------------------------------------------------------------
RE_ART = re.compile(
    r"^Art\.\s*(\d{1,4})\s*(?:º|°|o)?\s*(?:-\s*([A-Z]{1,2}))?\s*[\.\-–]?(?=\s|$)")
RE_CAB = re.compile(
    r"^(LIVRO|TÍTULO|CAPÍTULO|SEÇÃO|Seção|SUBSEÇÃO|Subseção)\s+"
    r"([IVXLCDM]+(?:-[A-Z])?|ÚNIC[AO]|Únic[ao])\b\s*[-–—.]?\s*(.*)$")
RE_ANEXO = re.compile(r"^ANEXO\s+([IVXLCDM]+(?:-[A-Z])?)\b\s*[-–—.]?\s*(.*)$")
NIVEIS = ["livro", "titulo", "capitulo", "secao", "subsecao"]


def nivel_de(palavra: str) -> str:
    p = unicodedata.normalize("NFKD", palavra.upper()).encode("ascii", "ignore").decode()
    return {"LIVRO": "livro", "TITULO": "titulo", "CAPITULO": "capitulo",
            "SECAO": "secao", "SUBSECAO": "subsecao"}[p]


def segmentar(paras: list[str]) -> list[dict]:
    unidades: list[dict] = []
    cab: dict[str, str] = {}
    pendente: str | None = None       # nível aguardando o nome na próxima linha
    atual: dict | None = None
    ultimo = (0, "")
    em_anexos = False

    def nova(tipo, rotulo, slug):
        u = {"tipo": tipo, "rotulo": rotulo, "slug": slug,
             "contexto": dict(cab), "paras": []}
        unidades.append(u)
        return u

    for p in paras:
        m_anx = RE_ANEXO.match(p)
        if m_anx and (ultimo[0] > 0 or em_anexos):
            em_anexos = True
            cab.clear()
            rom = m_anx.group(1)
            atual = nova("anexo", f"Anexo {rom}", f"anexo-{rom.lower()}")
            atual["nome"] = m_anx.group(2).strip()
            atual["paras"].append(p)
            pendente = None
            continue

        m_cab = RE_CAB.match(p)
        if m_cab and not em_anexos:
            nv = nivel_de(m_cab.group(1))
            # zera os níveis inferiores
            for n in NIVEIS[NIVEIS.index(nv):]:
                cab.pop(n, None)
            ident = f"{m_cab.group(1).capitalize()} {m_cab.group(2)}"
            nome = m_cab.group(3).strip()
            cab[nv] = f"{ident} – {nome}" if nome else ident
            pendente = None if nome else nv
            continue

        m_art = RE_ART.match(p)
        if m_art and not em_anexos:
            chave = (int(m_art.group(1)), m_art.group(2) or "")
            if chave > ultimo:
                ultimo = chave
                num, suf = chave
                rot = f"{num}{'º' if num < 10 else ''}{'-' + suf if suf else ''}"
                slug = f"art-{num}{'-' + suf.lower() if suf else ''}"
                atual = nova("artigo", f"Art. {rot}", slug)
                atual["paras"].append(p)
                pendente = None
                continue

        if pendente and len(p) < 200 and not INICIO_BLOCO.match(p):
            cab[pendente] = f"{cab[pendente]} – {p}"
            pendente = None
            continue
        pendente = None

        if atual is None:
            atual = nova("preambulo", "Ementa e preâmbulo", "preambulo")
        atual["paras"].append(p)

    # anexos: nome costuma vir na linha seguinte
    for u in unidades:
        if u["tipo"] == "anexo" and not u.get("nome") and len(u["paras"]) > 1:
            u["nome"] = u["paras"][1][:160]
    return unidades


def segmentar_blocos(paras: list[str]) -> list[dict]:
    """Para documentos sem artigos (ex.: Nota Técnica): blocos de tamanho fixo."""
    unidades, buf, tam = [], [], 0
    for p in paras:
        if tam + len(p) > 6000 and buf:
            unidades.append(buf)
            buf, tam = [], 0
        buf.append(p)
        tam += len(p)
    if buf:
        unidades.append(buf)
    out = []
    for i, b in enumerate(unidades, 1):
        titulo = next((p for p in b if re.match(r"^\d+(\.\d+)*\.?\s+\S", p) and len(p) < 140),
                      b[0][:120])
        out.append({"tipo": "bloco", "rotulo": f"Parte {i}", "slug": f"parte-{i}",
                    "nome": titulo, "contexto": {}, "paras": b})
    return out


def dividir_grandes(unidades: list[dict]) -> list[dict]:
    out = []
    for u in unidades:
        total = sum(len(p) for p in u["paras"])
        if total <= MAX_CHARS:
            out.append(u)
            continue
        partes, buf, tam = [], [], 0
        for p in u["paras"]:
            if tam + len(p) > MAX_CHARS and buf:
                partes.append(buf)
                buf, tam = [], 0
            buf.append(p)
            tam += len(p)
        partes.append(buf)
        for i, b in enumerate(partes, 1):
            v = dict(u)
            v["paras"] = b
            if i > 1:
                v["slug"] = f"{u['slug']}-parte-{i}"
                v["rotulo"] = f"{u['rotulo']} (parte {i} de {len(partes)})"
            else:
                v["rotulo"] = f"{u['rotulo']} (parte 1 de {len(partes)})"
            out.append(v)
    return out


# --------------------------------------------------------------------------
# HTML
# --------------------------------------------------------------------------
CSS = """
:root{--txt:#1d2733;--sec:#4d5b6a;--lnk:#0b5394;--bg:#fff;--ln:#d9dee4}
@media (prefers-color-scheme:dark){:root{--txt:#e3e7ec;--sec:#a6b1bd;--lnk:#8fbef0;--bg:#15191e;--ln:#333b44}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--txt);font:17px/1.65 Georgia,"Times New Roman",serif}
main{max-width:46rem;margin:0 auto;padding:2rem 1.25rem 4rem}
nav,footer,.ctx{font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;color:var(--sec)}
a{color:var(--lnk)}
h1{font-size:1.6rem;line-height:1.25;margin:.4rem 0 1.2rem}
.ctx{margin:0 0 .2rem}
p{margin:0 0 .8rem}
.tab{font:14px/1.5 system-ui,sans-serif;overflow-wrap:anywhere}
footer{border-top:1px solid var(--ln);margin-top:2.5rem;padding-top:1rem}
.pn{display:flex;justify-content:space-between;gap:1rem;margin-top:1.5rem}
ul{padding-left:1.2rem}li{margin:.2rem 0}
"""


def frase(s: str) -> str:
    """'DOS INSUMOS AGROPECUÁRIOS' -> 'Dos insumos agropecuários'."""
    if s and s.upper() == s:
        s = s.lower()
        return s[:1].upper() + s[1:]
    return s


def tema(u: dict) -> str:
    if u.get("nome"):
        return frase(u["nome"])
    for nv in reversed(NIVEIS):
        if nv in u["contexto"]:
            parte = u["contexto"][nv].split(" – ", 1)
            return frase(parte[1]) if len(parte) > 1 else parte[0]
    return ""


def resumo(u: dict) -> str:
    t = u["paras"][0] if u["paras"] else ""
    t = RE_ART.sub("", t).strip()
    return (t[:155] + "…") if len(t) > 156 else t


def pagina(fonte: dict, u: dict, ant: dict | None, prox: dict | None) -> str:
    e = html.escape
    tm = tema(u)
    titulo = f"{fonte['sigla']}, {u['rotulo']}" + (f": {tm}" if tm else "")
    def _niv(t: str) -> str:
        a, _, b = t.partition(" – ")
        return f"{a} – {frase(b)}" if b else a
    ctx = " › ".join(_niv(u["contexto"][n]) for n in NIVEIS if n in u["contexto"])
    corpo = []
    for p in u["paras"]:
        cls = ' class="tab"' if " | " in p else ""
        corpo.append(f"<p{cls}>{e(p)}</p>")
    pn = '<div class="pn">'
    pn += f'<a href="{ant["slug"]}.html">‹ {e(ant["rotulo"])}</a>' if ant else "<span></span>"
    pn += f'<a href="{prox["slug"]}.html">{e(prox["rotulo"])} ›</a>' if prox else "<span></span>"
    pn += "</div>"
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(titulo)}</title>
<meta name="description" content="{e(resumo(u))}">
<link rel="canonical" href="{e(BASE)}/{fonte['id']}/{u['slug']}.html">
<style>{CSS}</style></head>
<body><main>
<nav><a href="../index.html">Início</a> › <a href="index.html">{e(fonte['sigla'])}</a></nav>
{f'<p class="ctx">{e(ctx)}</p>' if ctx else ''}
<h1>{e(titulo)}</h1>
<article>
{chr(10).join(corpo)}
</article>
{pn}
<footer>Reprodução não oficial de {e(fonte['titulo'])}, gerada em {HOJE:%d/%m/%Y}.
Texto oficial: <a href="{e(fonte['url'])}">{e(fonte['url'])}</a>.
Trechos revogados ou com redação substituída foram omitidos; verifique sempre o texto oficial.</footer>
</main></body></html>
"""


def indice_fonte(fonte: dict, unidades: list[dict]) -> str:
    e = html.escape
    itens = "\n".join(
        f'<li><a href="{u["slug"]}.html">{e(u["rotulo"])}</a>'
        f'{": " + e(tema(u)) if tema(u) else ""}</li>' for u in unidades)
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(fonte['titulo'])}: índice por artigo</title>
<style>{CSS}</style></head>
<body><main>
<nav><a href="../index.html">Início</a></nav>
<h1>{e(fonte['titulo'])}</h1>
<p>Índice com {len(unidades)} páginas. Texto oficial em
<a href="{e(fonte['url'])}">{e(fonte['url'])}</a>.</p>
<ul>
{itens}
</ul>
</main></body></html>
"""


def indice_geral(geradas: list[tuple[dict, int]]) -> str:
    e = html.escape
    itens = "\n".join(
        f'<li><a href="{f["id"]}/index.html">{e(f["titulo"])}</a> ({n} páginas)</li>'
        for f, n in geradas)
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Reforma tributária do consumo: legislação por artigo (IBS, CBS, IS)</title>
<meta name="description" content="LC 214/2025, LC 227/2026, Decreto 12.955, Resoluções CGIBS e Nota Técnica, com uma página por artigo.">
<style>{CSS}</style></head>
<body><main>
<h1>Reforma tributária do consumo: legislação por artigo</h1>
<p>Reprodução não oficial, uma página por artigo, das normas do IBS, da CBS e do IS.
Atualizada em {HOJE:%d/%m/%Y}. Em caso de divergência, prevalece o texto oficial.</p>
<ul>
{itens}
</ul>
</main></body></html>
"""


# --------------------------------------------------------------------------
# Principal
# --------------------------------------------------------------------------
BASE = os.environ.get("SITE_BASE_URL", "https://example.github.io/repo").rstrip("/")


def main() -> int:
    cfg = json.loads((RAIZ / "fontes.json").read_text(encoding="utf-8"))
    SAIDA.mkdir(exist_ok=True)
    urls: list[str] = [f"{BASE}/index.html"]
    geradas: list[tuple[dict, int]] = []

    for fonte in cfg["fontes"]:
        raw = obter_bytes(fonte)
        if raw is None:
            continue
        try:
            if fonte["tipo"] == "planalto_html":
                unidades = segmentar(paragrafos_planalto(raw))
            elif fonte["tipo"] == "pdf_artigos":
                unidades = segmentar(paragrafos_pdf(raw))
            else:
                unidades = segmentar_blocos(paragrafos_pdf(raw))
        except Exception as ex:  # noqa: BLE001
            aviso(f"{fonte['id']}: erro ao processar ({ex})")
            continue
        unidades = dividir_grandes(unidades)
        if not unidades:
            aviso(f"{fonte['id']}: nenhum conteúdo extraído")
            continue

        # checagens de sanidade
        arts = [u for u in unidades if u["tipo"] == "artigo"]
        print(f"[{fonte['id']}] {len(unidades)} páginas ({len(arts)} de artigos)")
        amostra = [u for u in unidades if u["slug"] in ("art-138", "art-7-a", "anexo-ix")] or unidades[:2]
        det = "\n".join(
            f"--- {u['slug']} | tema: {tema(u)} | ctx: {' > '.join(u['contexto'].values())}\n"
            + "\n".join(p[:220] for p in u["paras"][:6]) for u in amostra)
        nota(f"{fonte['id']}: {len(unidades)} páginas, {len(arts)} artigos",
             f"primeira: {unidades[0]['slug']} | última: {unidades[-1]['slug']}\n"
             f"anexos: {', '.join(u['slug'] for u in unidades if u['tipo'] == 'anexo')}\n{det}")
        if fonte["id"] == "lc214":
            slugs = {u["slug"] for u in unidades}
            for obrig in ("art-138", "art-7-a", "anexo-ix"):
                if obrig not in slugs:
                    aviso(f"lc214: página esperada ausente: {obrig}")
            if len(arts) < 500:
                aviso(f"lc214: só {len(arts)} artigos extraídos (esperado > 500)")

        pasta = SAIDA / fonte["id"]
        pasta.mkdir(exist_ok=True)
        vistos: set[str] = set()
        for i, u in enumerate(unidades):
            base_slug, k = u["slug"], 2
            while u["slug"] in vistos:
                u["slug"] = f"{base_slug}-{k}"
                k += 1
            vistos.add(u["slug"])
        for i, u in enumerate(unidades):
            ant = unidades[i - 1] if i > 0 else None
            prox = unidades[i + 1] if i + 1 < len(unidades) else None
            (pasta / f"{u['slug']}.html").write_text(pagina(fonte, u, ant, prox), encoding="utf-8")
            urls.append(f"{BASE}/{fonte['id']}/{u['slug']}.html")
        (pasta / "index.html").write_text(indice_fonte(fonte, unidades), encoding="utf-8")
        urls.append(f"{BASE}/{fonte['id']}/index.html")
        geradas.append((fonte, len(unidades)))

    if not geradas:
        print("Nenhuma fonte processada.", file=sys.stderr)
        return 1

    (SAIDA / "index.html").write_text(indice_geral(geradas), encoding="utf-8")
    hoje = HOJE.isoformat()
    sm = ['<?xml version="1.0" encoding="UTF-8"?>',
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    sm += [f"<url><loc>{html.escape(u)}</loc><lastmod>{hoje}</lastmod></url>" for u in urls]
    sm.append("</urlset>")
    (SAIDA / "sitemap.xml").write_text("\n".join(sm), encoding="utf-8")
    (SAIDA / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {BASE}/sitemap.xml\n")
    chave = cfg.get("indexnow_key")
    if chave:
        (SAIDA / f"{chave}.txt").write_text(chave)
    (SAIDA / ".nojekyll").write_text("")
    (SAIDA / "urls.txt").write_text("\n".join(urls))

    print(f"\n{len(urls)} URLs geradas em {SAIDA}")
    if avisos:
        print("\nAVISOS:\n- " + "\n- ".join(avisos))
    return 0


if __name__ == "__main__":
    sys.exit(main())
