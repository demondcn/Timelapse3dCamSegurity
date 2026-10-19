@echo off
cd /d "%~dp0"
py recuperar_timelapse.py
if errorlevel 1 (
  echo.
  echo No se pudieron recuperar los videos. Revisa el mensaje anterior.
)
pause
