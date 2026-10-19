# Arquitectura de Timelapse3dCamSegurity

## Estado previo a esta fase

El programa original se concentra en `timelapse_fluidd.py` y tiene cuatro responsabilidades:

1. `Camera` mantiene una lectura RTSP continua en un hilo y conserva el fotograma mas reciente.
2. `PrinterEvents` escucha por WebSocket las respuestas nuevas de Moonraker y publica solamente los mensajes `capture 0` en una cola.
3. `run()` elimina eventos duplicados, programa cada foto con reloj monotonico y la escribe como `capa_NNNNNN.jpg` despues de `retardo_captura_seg`.
4. Al terminar la impresion, `build_videos()` exporta MP4 horizontal y vertical. En paralelo, FFmpeg puede copiar el stream RTSP completo a `video_completo.mkv`.

`recuperar_timelapse.py` repite parte de la exportacion para reconstruir los videos desde una sesion antigua. Los BAT son puntos de entrada para instalar, calibrar, grabar y recuperar.

## Flujo de datos conservado

```text
Tapo C210 --RTSP--> Camera --ultimo frame--> JPG original
                                               |
Moonraker --WebSocket capture 0--> cola --retardo configurable

Tapo C210 --RTSP--> FFmpeg --copia sin recodificar--> video_completo.mkv
```

La integracion de calidad se coloca despues de finalizar las capturas. No cambia el listener, la deduplicacion, el retardo, el nombre de los originales ni la grabacion continua:

```text
JPG originales (solo lectura)
    -> procesador OpenCV de secuencia
    -> exportaciones/<perfil>/fotogramas_procesados/
       -> estandar: VideoWriter OpenCV, 1080p30
       -> alta_calidad: FFmpeg/Lanczos, 4K60
       -> ultra_ia: Real-ESRGAN sobre copias -> FFmpeg/Lanczos, 4K60
```

Real-ESRGAN NCNN Vulkan es una etapa opcional entre OpenCV y el JPG mejorado. Si no esta instalado, Ultra registra el fallo y puede crear Alta calidad desde los originales. No se necesita CUDA, PyTorch ni paquetes Python adicionales.

## Invariantes de seguridad y operacion

- El programa consulta el estado y escucha mensajes de Moonraker; nunca envia G-code.
- `config.json` y todo `config*.json`, salvo el ejemplo ficticio, quedan ignorados por Git.
- Los JPG originales nunca se sobrescriben. El procesador rechaza una carpeta de salida igual o contenida de forma incorrecta en el origen.
- Los nombres y argumentos de procesos externos se pasan como listas, sin una shell.
- Las URL con credenciales no se imprimen.
- Una falla de mejora no elimina fotos ni el video completo. La sesion permanece recuperable.
- Cada exportacion usa una carpeta nueva (`perfil`, `perfil_002`, etc.) y nunca reemplaza archivos generados.
- La duracion depende de fotos/segundo, no de los FPS de salida. Los fotogramas se duplican sin interpolacion de movimiento.

## Modulos implementados

- `mejora_imagenes.py`: validacion de configuracion, analisis temporal y procesamiento OpenCV; adaptador opcional NCNN.
- `exportador_video.py`: manifiesto concat y dos salidas H.264 configurables.
- `perfiles_exportacion.py`: seleccion de perfil, salidas versionadas, OpenCV 1080p, FFmpeg 4K y fallback de IA.
- `mejorar_fotos.py`: CLI reutilizable para sesiones antiguas.
- `timelapse_fluidd.py`: captura existente sin cambios y llamada al perfil solamente durante el cierre poscaptura.
- `tests/`: pruebas sinteticas que no acceden a red, impresora ni camara.

## Estrategia contra parpadeo

No se usaran ecualizacion ni balance de blancos automaticos independientes por fotografia. Primero se analiza la luminancia robusta de toda la secuencia. Las ganancias de exposicion se limitan y se suavizan temporalmente; contraste, color y nitidez usan parametros fijos para todos los fotogramas. Esto corrige variaciones moderadas sin crear saltos visibles.
