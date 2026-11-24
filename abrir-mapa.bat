@echo off
rem Abre el mapa de OSINT Maps con doble clic (Windows): la version completa.
rem Mientras esta ventana siga abierta se guarda el historico de la ciudad (el pulso)
rem y la web publicada recibe los datos al arrancar y cada 15 minutos.
rem Para usarlo desde el movil en la misma wifi:  abrir-mapa.bat --red
rem Solo el mapa, sin guardar ni publicar nada:  .venv\Scripts\osintmaps.exe servir
rem Para abrir la sala de control en vez del mapa:  abrir-mapa.bat --sala
cd /d "%~dp0"
if not exist ".venv\Scripts\osintmaps.exe" (
  echo Falta instalar el programa. En esta carpeta, ejecuta:
  echo    python -m venv .venv
  echo    .venv\Scripts\pip install -e .
  pause
  exit /b 1
)
".venv\Scripts\osintmaps.exe" servir --pulso --publicar-datos %*
pause
