# Meta Ads Library Explorer (`mae`)

Herramienta para explorar la **Meta Ad Library** con una interfaz web:
buscar anuncios, trackear anunciantes y analizar creatividades con Claude.

## 🚀 Quickstart en 3 pasos (interfaz web)

> Requiere tener **Python 3.10+** instalado. Si no lo tenés:
> Windows/Mac → bajalo de https://www.python.org/downloads/ (marcá **"Add Python to PATH"** durante la instalación).
> Linux → `sudo apt install python3 python3-venv python3-pip`.

### Paso 1 — Clonar el proyecto

Abrí una **terminal** (en Windows: "PowerShell" o "CMD"; en Mac/Linux: "Terminal") y pegá:

```bash
git clone https://github.com/ferxtr/test.git meta-ads-explorer
cd meta-ads-explorer
```

### Paso 2 — Instalar (una sola vez)

**Mac / Linux:**
```bash
bash install.sh
```

**Windows:**
```bash
install.bat
```

Esto crea un entorno virtual, instala las dependencias e instala Chrome para el scraper. Tarda 3-5 min la primera vez.

> Después de instalar, abrí el archivo `.env` que se creó solo y pegá tu `ANTHROPIC_API_KEY` (sacala en https://console.anthropic.com/settings/keys). Sin esa key todo funciona menos el análisis con IA.

### Paso 3 — Abrir la app

**Mac / Linux:**
```bash
bash start.sh
```

**Windows:** doble click en `start.bat`.

Se abre solo tu navegador en `http://localhost:8501` con la interfaz:

- 🔍 **Buscar** — pegás palabra clave + país, le das "Buscar"
- 📺 **Páginas trackeadas** — agregás cuentas a seguir y re-scrapeás con un click
- 🤖 **Analizar con IA** — Claude mira las creatividades y devuelve ángulo, hook, pain points, calidad
- 📊 **Reporte** — gráficos con los patrones encontrados
- 📥 **Exportar** — descargás todo a CSV o JSON

Cuando termines de usarla, cerrá la terminal. Para usarla otra vez: repetí el Paso 3.

---

## ¿Y subirlo a internet (que cualquiera pueda entrar a una URL)?

**Vercel NO sirve** para esto — necesita correr un Chrome real durante varios minutos y guardar archivos, cosas que Vercel no permite. Para tener una URL pública usá:

- **Render** (https://render.com) — tier gratuito, deploy desde GitHub con Docker.
- **Railway** (https://railway.app) — $5 crédito inicial, deploy en 2 clicks.
- **Streamlit Community Cloud** (https://streamlit.io/cloud) — gratis pero con limitaciones de browser.

Si querés que te lo arme con uno de estos, decime cuál y te agrego el `Dockerfile` o config necesaria.

> Alternativa **sin tener que instalar nada en tu compu**: usar **GitHub Actions** (workflow ya incluido en `.github/workflows/`) que corre el scraping en la nube de GitHub gratis y commitea los resultados al repo. Pero no tiene interfaz web, accedés a los datos descargando el archivo `meta_ads.db`.

---

## Aclaración legal

Este programa scrapea el frontend público de la Ad Library (no usa la API oficial),
por lo que opera contra los ToS de Meta. Usalo en entornos donde tengas autorización,
con rate-limit prudente y sin distribuir datos personales. Es una herramienta de research,
no de producción a escala.

---

## Si preferís usar comandos (terminal)

| Comando             | Para qué sirve                                                          |
| ------------------- | ----------------------------------------------------------------------- |
| `mae web`           | Abre la interfaz web (igual que `start.sh`)                             |
| `mae search`        | Buscar por palabra clave en un país                                     |
| `mae page`          | Scrapear todos los anuncios de una página y opcionalmente trackearla    |
| `mae track`         | Listar / agregar páginas a la lista de tracking                         |
| `mae snapshot`      | Re-scrapear todas las páginas trackeadas y registrar cambios            |
| `mae analyze`       | Analizar copy + creatividades con Claude                                |
| `mae report`        | Reporte agregado en consola                                             |
| `mae export`        | Exportar a CSV o JSON                                                   |

## Instalación manual (si los scripts fallan)

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

## Correr en la nube con GitHub Actions

El repo trae dos workflows listos para usar sin tener tu compu prendida.

### Setup inicial (una sola vez)

1. **Pushear a GitHub** (ya está hecho si seguiste el flujo).
2. En el repo → **Settings → Secrets and variables → Actions**:
   - **Secret** `ANTHROPIC_API_KEY` → tu clave de Claude (para el paso de análisis).
   - **Variable** `MAE_COUNTRY` (opcional) → ISO-2 del país, default `AR`.
   - **Variable** `MAE_CLAUDE_MODEL` (opcional) → `claude-sonnet-4-6` (default) o el que prefieras.
3. En **Settings → Actions → General**, scrolleá hasta "Workflow permissions" y dejá
   marcada **"Read and write permissions"** (necesario para que el bot pueda commitear
   la DB de vuelta al repo).

### Workflow 1 — Agregar páginas a tracking (manual)

`.github/workflows/track-page.yml`

En GitHub → **Actions → "Track a new page" → Run workflow**. Te pide:

- `page`: el `page_id` numérico o la URL completa de Ad Library.
- `country`: ISO-2 (default `AR`).
- `notes`: nota opcional para recordar qué es esa página.
- `max_ads`: cuántos anuncios traer en la primera pasada (default 80).

Esto scrapea la página, la agrega a `tracked_pages` y commitea `meta_ads.db`.

### Workflow 2 — Snapshot + análisis diario

`.github/workflows/snapshot.yml`

Corre **todos los días a las 08:00 UTC** (~05:00 ART) automáticamente:

1. Re-scrapea cada página trackeada.
2. Detecta nuevos anuncios y registra snapshots.
3. Analiza los anuncios nuevos con Claude.
4. Commitea `meta_ads.db` y `report.txt` al repo.
5. Sube `meta_ads.db` + creatividades como artifact (descargable 14 días).

También podés dispararlo a mano en **Actions → "Daily Ad Library snapshot" → Run workflow**.

### Tip: cómo cambiar el horario

Editá la línea `cron:` en `snapshot.yml`. Por ejemplo `'0 12 * * *'` para mediodía UTC.
Formato: minuto / hora / día / mes / día-semana.

### ¿Y la DB queda en el repo?

Sí, `meta_ads.db` se commitea con `[skip ci]`. Para repos privados es ideal: tenés
versionado del histórico de anuncios. Si la DB crece mucho (varios MB), considerá
mover a un volumen externo o migrar a Postgres.

## Receta alternativa: cron en tu máquina

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
