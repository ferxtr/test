@echo off
REM Instalador one-shot para Windows.
REM Uso: doble click o ejecutar 'install.bat' en CMD/PowerShell.

echo.
echo Meta Ads Explorer - Instalador
echo ------------------------------------

where python >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo Python no esta instalado.
    echo Descargalo desde https://www.python.org/downloads/
    echo IMPORTANTE: durante la instalacion marca "Add Python to PATH"
    pause
    exit /b 1
)

if not exist .venv (
    echo Creando entorno virtual...
    python -m venv .venv
)

call .venv\Scripts\activate.bat

echo Instalando dependencias (puede tardar 2-3 min)...
pip install --quiet --upgrade pip
pip install --quiet -e .

echo Instalando Chrome para Playwright (puede tardar 1-2 min)...
playwright install chromium

if not exist .env (
    copy .env.example .env
    echo.
    echo Cree el archivo .env. Editalo y pega tu ANTHROPIC_API_KEY.
)

echo.
echo Listo. Para abrir la app ejecuta:
echo.
echo    .venv\Scripts\activate
echo    mae web
echo.
echo Y se abre solo en el navegador en http://localhost:8501
echo.
pause
