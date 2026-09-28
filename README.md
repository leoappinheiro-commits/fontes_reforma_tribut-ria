# Fontes da reforma tributária por artigo

Site estático com a LC 214/2025 (compilada), LC 227/2026, Decreto 12.955, Resoluções CGIBS 6 e 13 e a Nota Técnica, com **uma página por artigo**. Serve de fonte de conhecimento para o agente do Copilot, que só lê sites públicos via Bing.

O GitHub baixa as normas, gera o site, publica no GitHub Pages e avisa o Bing, sozinho, toda segunda-feira.

## Publicação (uma vez, uns 15 minutos)

1. **Crie o repositório.** No GitHub, crie um repositório **público** chamado `fontes-reforma` (Pages gratuito exige repositório público).
2. **Envie os arquivos.** Em "Add file > Upload files", arraste o conteúdo desta pasta. Confira se a pasta `.github/workflows/publicar.yml` subiu: alguns sistemas escondem pastas que começam com ponto. Se não subiu, use "Add file > Create new file", digite `.github/workflows/publicar.yml` como nome e cole o conteúdo.
3. **Ative o Pages.** Em Settings > Pages > Build and deployment > Source, escolha **GitHub Actions**.
4. **Rode.** Em Actions > "Publicar fontes da reforma" > Run workflow.
5. **Leia o log** do passo "Gerar site". A linha `[lc214] N páginas` deve mostrar mais de 500 artigos, e não pode haver aviso de `art-138`, `art-7-a` ou `anexo-ix` ausentes.
6. **Abra o site:** `https://SEU_USUARIO.github.io/fontes-reforma/lc214/art-138.html`.

## Se o download de alguma fonte falhar

Planalto, CGIBS e legisweb podem bloquear servidores do GitHub (erro 403 no log). Nesse caso, baixe pelo navegador e salve em `fontes_manuais/` com o nome indicado em `fontes.json`:

| Fonte | Arquivo |
|---|---|
| LC 214 compilada | `fontes_manuais/lc214.htm` (no navegador: Salvar como > "Página da Web, somente HTML") |
| LC 227/2026 | `fontes_manuais/lc227.htm` (ou preencha a URL em `fontes.json`) |
| Decreto 12.955 | `fontes_manuais/decreto12955.htm` |
| Res. CGIBS 6 e 13 | `fontes_manuais/res-cgibs-6.pdf`, `fontes_manuais/res-cgibs-13.pdf` |
| Nota Técnica | `fontes_manuais/nota-tecnica.pdf` |

Arquivo manual tem prioridade sobre o download. Lembre de substituí-lo quando a norma mudar.

**Decreto 12.955:** é de 29/04/2026 (regulamento da CBS); a URL já aponta para a pasta /2026/ do Planalto.

## Indexação no Bing (sem isso o agente não enxerga nada)

- O workflow já avisa o Bing via IndexNow após cada publicação.
- Recomendado: cadastre o site no **Bing Webmaster Tools** (bing.com/webmasters) e envie `https://SEU_USUARIO.github.io/fontes-reforma/sitemap.xml`. Lá você acompanha quantas páginas foram indexadas.
- Teste no próprio Bing: `site:SEU_USUARIO.github.io art. 138 insumos`. Só configure o agente quando isso retornar resultados. A indexação pode levar alguns dias.

## Configuração do agente no Copilot

**Conhecimento (1 link, profundidade 1):** `https://SEU_USUARIO.github.io/fontes-reforma`

Os outros links podem sair: tudo está neste site.

**Trecho para a instrução**, substituindo a seção "Fontes autorizadas":

> Suas fontes são as páginas de https://SEU_USUARIO.github.io/fontes-reforma, que reproduzem a LC 214/2025 (com alterações da LC 227/2026), o Decreto 12.955/2026, as Resoluções CGIBS 6/2026 e 13/2026 e a Nota Técnica, com uma página por artigo. O título de cada página traz a norma e o número do artigo (ex.: "LC 214/2025, Art. 138: ..."). Busque sempre pelo número do artigo e pelo termo técnico. Responda exclusivamente com base no texto dos trechos recuperados. Se o trecho recuperado não contiver o dispositivo aplicável, busque novamente pelo número do artigo; se ainda assim não o localizar, informe que o dispositivo não foi recuperado e não responda com base em conhecimento próprio. Não use valores ilustrativos de alíquota que não constem das fontes.

## Como funciona

- `scripts/build_site.py`: baixa as fontes, **remove o texto tachado do Planalto** (redações revogadas ou substituídas, que o compilado mantém riscadas e que o agente leria como vigentes), fatia por artigo e anexo, e gera HTML, `sitemap.xml` e `robots.txt`. Anexos e artigos longos viram "parte 1, parte 2…".
- `scripts/indexnow.py`: envia as URLs ao IndexNow.
- `fontes.json`: lista de fontes. Para incluir uma nova norma, acrescente um item com `tipo` `planalto_html`, `pdf_artigos` (PDF com artigos) ou `pdf_blocos` (PDF sem artigos, como notas técnicas).
- As páginas trazem aviso de reprodução não oficial e link para o texto oficial. Texto de lei é de domínio público (Lei 9.610/98, art. 8º, IV).
