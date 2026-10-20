# Arquitectura

El proyecto tiene tres modulos Python activos:

- `app/timelapse_fluidd.py`: lee la camara RTSP y los eventos nuevos `capture 0` de Moonraker, guarda los JPG y dispara la exportacion al terminar.
- `app/exportador_video.py`: crea los MP4 horizontal y vertical con FFmpeg.
- `app/recuperar_timelapse.py`: reconstruye ambos MP4 desde una sesion que conserva los JPG.

```text
Moonraker --capture 0--> cola --retardo--> ultimo frame Tapo --> capa_NNNNNN.jpg
                                                              |
                                                              +--> FFmpeg --> horizontal.mp4
                                                                          --> vertical.mp4
```

La deteccion de un primer `capture 0` tambien marca que hubo una impresion activa. Esto permite reconocer posteriormente `complete`, `cancelled`, `error` o `standby` aunque una consulta inicial de estado haya fallado.

Los JPG son la fuente recuperable y nunca se sobrescriben. La exportacion escribe primero archivos MP4 temporales y solo reemplaza el destino cuando FFmpeg termina correctamente.

No hay procesamiento mejorado, perfiles de calidad ni Real-ESRGAN en el flujo actual.
