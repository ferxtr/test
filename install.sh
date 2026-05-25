#!/usr/bin/env bash
# Instalador one-shot para Mac y Linux.
# Uso:  bash install.sh

set -e

echo "🎯 Meta Ads Explorer — Instalador"
echo "──────────────────────────────────"

if ! command -v python3 >/dev/null 2>&1; then
    echo "❌ Python 3 no está instalado."
    echo "   Mac:    instalá desde https://www.python.org/downloads/ o 'brew install python'"
    echo "   Linux:  sudo apt install python3 python3-venv python3-pip"
    exit 1
fi

PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')
echo "✓ Python $PY_VER detectado"

if [ ! -d ".venv" ]; then
    echo "→ Creando entorno virtual (.venv)…"
    python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

echo "→ Instalando dependencias (puede tardar 2-3 min)…"
pip install --quiet --upgrade pip
pip install --quiet -e .

echo "→ Instalando Chrome para Playwright (puede tardar 1-2 min)…"
playwright install chromium

if [ ! -f ".env" ]; then
    cp .env.example .env
    echo ""
    echo "📝 Creé el archivo .env. Editalo y pegá tu ANTHROPIC_API_KEY."
    echo "   (sin esa key, todo funciona menos el análisis con IA)"
fi

echo ""
echo "✅ Listo. Para abrir la app web ejecutá:"
echo ""
echo "   source .venv/bin/activate"
echo "   mae web"
echo ""
echo "Y se abre solo en el navegador en http://localhost:8501"
