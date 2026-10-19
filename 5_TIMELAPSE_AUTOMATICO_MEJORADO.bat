@echo off
cd /d "%~dp0"
py timelapse_fluidd.py grabar
if errorlevel 1 (
  echo.
  echo El timelapse termino con un error. Las fotos ya guardadas no se eliminan.
)
pause
