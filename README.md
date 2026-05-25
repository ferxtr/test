# Meta Ads Library Explorer (`mae`)

Herramienta CLI en Python para explorar la **Meta Ad Library** de forma inteligente:
buscar anuncios, trackear anunciantes en el tiempo y analizar creatividades con Claude (vision).

> **Aclaración legal**: este programa scrapea el frontend público de la Ad Library
> (no usa la API oficial de Graph), por lo que opera contra los ToS de Meta. Usalo en
> entornos donde tengas autorización, con rate-limit prudente y sin distribuir datos
> personales sensibles. Es una herramienta de research, no de producción a escala.

## Capacidades

| Comando             | Para qué sirve                                                          |
| ------------------- | ----------------------------------------------------------------------- |
| `mae search`        | Buscar por palabra clave en un país, persiste a SQLite                  |
| `mae page`          | Scrapear todos los anuncios de una página y opcionalmente trackearla    |
| `mae track`         | Listar / agregar páginas a la lista de tracking                         |
| `mae snapshot`      | Re-scrapear todas las páginas trackeadas y registrar cambios            |
| `mae analyze`       | Analizar copy + creatividades con Claude (vision) → JSON estructurado   |
| `mae report`        | Reporte agregado: ángulos top, formatos, pain points, calidad promedio  |
| `mae export`        | Exportar a CSV o JSON                                                   |

## Instalación

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
playwright install chromium    # o: mae install-browser
cp .env.example .env           # poné tu ANTHROPIC_API_KEY
```

## Uso típico

```bash
# 1) Buscar "curso ingles" en Argentina
mae search "curso ingles" -c AR --max 80

# 2) Trackear una página específica (la pasás por page_id o URL completa)
mae page 1234567890 --track --notes "competidor directo"

# 3) Snapshot diario de todas las páginas trackeadas (ideal en un cron)
mae snapshot --max 100

# 4) Analizar lo nuevo con Claude
mae analyze --limit 20

# 5) Reporte de ángulos y patrones
mae report

# 6) Exportar para Excel/Looker
mae export ./out.csv
```

## Cómo encontrar un `page_id`

1. Abrí la Ad Library en el browser: `https://www.facebook.com/ads/library/`
2. Buscá el anunciante.
3. Click en el resultado → URL será algo como
   `…?…&view_all_page_id=1234567890`. Ese número es el `page_id`.
4. También podés pasarle la URL completa directamente: `mae page "https://..."`.

## Cómo funciona el scraping

`scraper.py` lanza Chromium con Playwright y **escucha las respuestas XHR** que
hace el SPA de la Ad Library a `/api/graphql/`. De cada respuesta extrae
recursivamente todos los dicts que tienen `ad_archive_id` y los normaliza al
modelo `Ad`. Scrollea progresivamente hasta:

- alcanzar `--max` anuncios, o
- 4 scrolls seguidos sin nuevos resultados, o
- llegar al límite de scrolls (40).

Como Meta cambia el shape de las respuestas seguido, el parser es defensivo:
si una key cambia, los campos opcionales quedan `None` pero el ad sigue
guardándose con el JSON crudo en la columna `raw_json`. Eso te deja recuperar
campos nuevos sin re-scrapear.

## Análisis con Claude

Para cada anuncio, el analyzer:

1. Descarga hasta `--images N` creatividades (default 2) a `./creatives/<ad_id>/`.
2. Las codifica en base64 y se las pasa a Claude junto al copy (title, body, CTA).
3. Pide un JSON con: `angle`, `hook`, `format`, `audience_signal`, `pain_points`,
   `promises`, `cta_strength`, `ad_type`, `originality`, `estimated_quality`,
   `red_flags`, `key_phrases`, `summary`.
4. Persiste el JSON en la tabla `analyses`.

El system prompt se cachea con `cache_control: ephemeral` para abaratar runs
en lote (el segundo análisis en adelante usa cache hit).

## Esquema de la base

- `ads` — fila por anuncio (último estado conocido + `raw_json` crudo).
- `snapshots` — fila por cada vez que vimos el anuncio (timestamp + estado).
- `searches` — log de cada búsqueda lanzada.
- `tracked_pages` — qué páginas estoy siguiendo.
- `analyses` — resultados del análisis con Claude.

Para ver la base directo: `sqlite3 meta_ads.db`.

## Receta: tracking diario con cron

```bash
# crontab -e
0 8 * * * cd /ruta/al/proyecto && /ruta/.venv/bin/mae snapshot --max 100 && \
          /ruta/.venv/bin/mae analyze --limit 30
```

## Tips para que el scraping aguante

- Corré con `MAE_HEADLESS=false` la primera vez para ver qué muestra Meta y
  resolver cualquier modal de cookies/login.
- Si te empieza a pedir login, abrí una sesión real en el browser → exportá las
  cookies → cargalas como `storage_state` (extensión natural del scraper).
- Subí `MAE_SCROLL_DELAY` a 3-4 segundos si ves que cargás muchas páginas y
  Meta empieza a tirarte rate-limit.

## Estructura

```
meta_ads_explorer/
├── cli.py         # comandos Typer
├── scraper.py     # Playwright + parser GraphQL
├── storage.py     # SQLite (ads, snapshots, analyses, tracked_pages)
├── analyzer.py    # Claude vision
├── models.py      # Pydantic Ad
└── config.py      # carga .env
```
