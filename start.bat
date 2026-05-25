@echo off
REM Levantar la app web. Doble click en este archivo.
if not exist .venv (
    echo Falta instalar primero. Ejecuta install.bat
    pause
    exit /b 1
)
call .venv\Scripts\activate.bat
mae web
