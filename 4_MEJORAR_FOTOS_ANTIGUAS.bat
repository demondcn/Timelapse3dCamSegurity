@echo off
cd /d "%~dp0"
if "%~1"=="" (
  py mejorar_fotos.py
) else (
  py mejorar_fotos.py --carpeta "%~1"
)
if errorlevel 1 (
  echo.
  echo No se pudo completar la mejora. Revisa el mensaje anterior.
)
pause
