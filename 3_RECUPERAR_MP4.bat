@echo off
cd /d "%~dp0"
if "%~1"=="" (
  py -m app.recuperar_timelapse
) else (
  py -m app.recuperar_timelapse --carpeta "%~1"
)
if errorlevel 1 (
  echo.
  echo No se pudieron recuperar los videos. Revisa el mensaje anterior.
)
pause
