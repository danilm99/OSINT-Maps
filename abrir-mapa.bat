@echo off
rem Abre el mapa de OSINT Maps con doble clic (Windows).
rem Para usarlo desde el movil en la misma wifi:  abrir-mapa.bat --red
cd /d "%~dp0"
if not exist ".venv\Scripts\osintmaps.exe" (
  echo Falta instalar el programa. En esta carpeta, ejecuta:
  echo    python -m venv .venv
  echo    .venv\Scripts\pip install -e .
  pause
  exit /b 1
)
".venv\Scripts\osintmaps.exe" servir %*
pause
