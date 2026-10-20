@echo off
title Timelapse automatico Tapo + Creality Hi
cd /d "%~dp0"
echo El MP4 se crea cuando termine la impresion o cuando pulses Ctrl+C.
echo NO cierres esta ventana con la X: eso impediria finalizar el video.
echo.
py -m app.timelapse_fluidd
if errorlevel 1 (
  echo.
  echo El timelapse termino con un error. Las fotos ya guardadas no se eliminan.
  echo Puedes reconstruirlo con 3_RECUPERAR_MP4.bat.
)
pause

