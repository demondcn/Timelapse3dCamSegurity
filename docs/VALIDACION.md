# Validacion

La prueba automatizada usa fotografias sinteticas y comprueba que `app/exportador_video.py` genera:

- H.264 con formato `yuv420p`.
- Salida horizontal y vertical con las dimensiones configuradas.
- Duracion correspondiente a `cantidad de fotos / fotos_por_segundo`.

Ejecucion:

```powershell
py -m pip install -r requirements-dev.txt
py -m pytest -q
```

La prueba no accede a la impresora, Moonraker ni la camara.
