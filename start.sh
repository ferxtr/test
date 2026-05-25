#!/usr/bin/env bash
# Levantar la app web. Uso: bash start.sh
set -e
if [ ! -d ".venv" ]; then
    echo "❌ Falta instalar primero. Ejecutá: bash install.sh"
    exit 1
fi
# shellcheck disable=SC1091
source .venv/bin/activate
mae web
