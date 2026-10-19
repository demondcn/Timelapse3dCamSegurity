# Timelapse3dCamSegurity

Timelapses por capa para una Tapo C210 y una impresora conectada a Moonraker/Fluidd. El programa escucha eventos nuevos `capture 0`, toma una fotografia tras el retardo configurado, conserva los JPG originales, genera copias mejoradas y exporta MP4 horizontal y vertical.

El programa **no envia G-code** ni modifica el firmware. La grabacion RTSP continua sigue siendo independiente del timelapse.

## Instalacion

Requisitos: Windows, Python 3.10 o posterior, acceso local a Moonraker y a la Tapo, y FFmpeg en `PATH`.

1. Instala FFmpeg, por ejemplo con `winget install --id Gyan.FFmpeg -e`, y abre una consola nueva.
2. Ejecuta `0_INSTALAR.bat`.
3. Copia `config.example.json` como `config.json`.
4. Sustituye solamente en `config.json` las direcciones y credenciales ficticias por las locales.
5. Ejecuta `1_PROBAR_TIEMPOS.bat` durante una impresion corta y elige el retardo en el que cabezal y cama esten quietos.

`config.json` esta ignorado por Git. Nunca se debe renombrar como ejemplo ni adjuntar a incidencias.

## Uso

- `2_TIMELAPSE_AUTOMATICO.bat`: captura y, al terminar, aplica la mejora y exporta los videos.
- `5_TIMELAPSE_AUTOMATICO_MEJORADO.bat`: punto de entrada explicito equivalente, con mensaje de error mas visible.
- `4_MEJORAR_FOTOS_ANTIGUAS.bat`: mejora la sesion mas reciente y regenera los MP4.
- Arrastrar una carpeta de sesion sobre `4_MEJORAR_FOTOS_ANTIGUAS.bat`: procesa esa carpeta concreta.
- `3_RECUPERAR_MP4.bat`: reconstruye videos desde los JPG originales con el perfil configurado.

Desde consola:

```powershell
py mejorar_fotos.py --carpeta "resultados\AAAA-MM-DD_HH-MM-SS_TIMELAPSE"
py mejorar_fotos.py --carpeta "resultados\..." --perfil estandar
py mejorar_fotos.py --carpeta "resultados\..." --perfil alta_calidad
py mejorar_fotos.py --carpeta "resultados\..." --perfil ultra_ia
py mejorar_fotos.py --carpeta "resultados\..." --sin-video
```

Cada sesion mantiene esta estructura:

```text
resultados/AAAA-MM-DD_HH-MM-SS_TIMELAPSE/
  capa_000001.jpg                 originales inmutables
  video_completo.mkv              stream continuo, si esta habilitado
  exportaciones/
    ultra_ia/                      nunca reemplaza resultados anteriores
      fotogramas_procesados/
        capa_000001.jpg            copias OpenCV + IA
        informe_mejora.json
      timelapse_horizontal.mp4
      timelapse_tiktok_9x16.mp4
      informe_exportacion.json
    ultra_ia_002/                  segunda ejecucion del mismo perfil
```

Cada ejecucion reserva un directorio nuevo. Los MP4, informes y fotogramas de ejecuciones anteriores no se reemplazan. Si Ultra IA no puede iniciar Real-ESRGAN, registra el fallo y usa `fallback_ultra` sobre nuevas copias de los originales. Nada elimina una captura existente.

## Perfiles de exportacion

| Perfil | Procesamiento | Salida horizontal | Salida vertical |
|---|---|---:|---:|
| `estandar` | OpenCV, codec MP4V | 1920 x 1080, 30 FPS | 1080 x 1920, 30 FPS |
| `alta_calidad` | OpenCV + FFmpeg/Lanczos | 3840 x 2160, 60 FPS | 2160 x 3840, 60 FPS |
| `ultra_ia` | OpenCV + Real-ESRGAN NCNN Vulkan + FFmpeg/Lanczos | 3840 x 2160, 60 FPS | 2160 x 3840, 60 FPS |

El perfil inicial es `ultra_ia`. La dependencia de IA sigue siendo opcional porque el fallback inicial es `alta_calidad`.

Todos los perfiles parten directamente de `capa_*.jpg`; nunca usan la salida de otro perfil. La duracion objetivo siempre es `cantidad de fotos / fotos_por_segundo`. Para 30 o 60 FPS se generan exactamente `round(duracion x FPS)` fotogramas seleccionando y duplicando originales. `interpolacion_movimiento` es `false` y el sistema rechaza activarla: no usa flujo optico, mezcla ni `minterpolate`.

## Procesamiento y estabilidad

El procesador analiza primero toda la secuencia. Usa la mediana de luminancia, una referencia temporal bidireccional y ganancias limitadas. No aplica balance de blancos ni ecualizacion automatica independiente por foto. Despues aplica:

1. reduccion moderada de ruido con Non-local Means;
2. exposicion estabilizada sobre luminancia, sin variar el color;
3. contraste fijo para toda la secuencia;
4. mascara de enfoque moderada con parametros fijos;
5. escritura JPG atomica dentro de la carpeta versionada del perfil.

FFmpeg usa escalado Lanczos, H.264 configurable, rango TV, BT.709, `faststart` y salida compatible `yuv420p` por defecto.

## Configuracion

Los valores completos y sus tipos estan en `config.example.json`.

| Clave | Efecto | Valor inicial |
|---|---|---:|
| `retardo_captura_seg` | Retardo despues de `capture 0`; no cambia con esta fase | `0.3` |
| `fotos_por_segundo` | Velocidad narrativa del timelapse | `6.0` |
| `exportacion.perfil` | Perfil automatico inicial | `ultra_ia` |
| `exportacion.fallback_ultra` | Perfil usado si NCNN falla; `null` impide fallback | `alta_calidad` |
| `exportacion.interpolacion_movimiento` | Debe permanecer desactivada | `false` |
| `exportacion.perfiles.*.fps` | FPS propios de cada perfil | `30 / 60 / 60` |
| `mejora.reduccion_ruido` | Intensidad Non-local Means, 0 desactiva | `3.0` |
| `mejora.exposicion_ev` | Ajuste global, limitado a -1..+1 EV | `0.0` |
| `mejora.estabilizar_exposicion` | Compensa variaciones temporales | `true` |
| `mejora.ganancia_minima/maxima` | Limites contra sobrecorreccion | `0.9 / 1.1` |
| `mejora.suavizado_temporal` | Peso de la referencia global | `0.85` |
| `mejora.contraste` | Contraste fijo; 1 no cambia | `1.05` |
| `mejora.nitidez` | Cantidad de mascara de enfoque | `0.35` |
| `mejora.calidad_jpg` | Calidad de las copias | `95` |
| `exportacion.perfiles.*.crf` | Calidad H.264; menor es mayor calidad/tamano | `16 / 15` |
| `exportacion.perfiles.*.preset` | Compresion FFmpeg | `slow` |

Las dimensiones, FPS, CRF y preset son configurables dentro de cada perfil. Los valores iniciales corresponden exactamente a 1080p30 y 4K60.

## Real-ESRGAN NCNN Vulkan opcional

La integracion usa el ejecutable portatil oficial; no instala PyTorch, CUDA ni paquetes Python. Ultra IA lo activa solamente sobre copias dentro de su propia carpeta de exportacion.

1. Descarga el paquete Windows desde las [versiones oficiales de Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN-ncnn-vulkan/releases).
2. Extraelo como `herramientas/realesrgan-ncnn-vulkan/`, conservando el `.exe` y la carpeta `models` juntos.
3. Actualiza el controlador grafico con soporte Vulkan.
4. Prueba primero una sesion corta y luego configura:

```json
"real_esrgan": {
  "habilitado": false,
  "ejecutable": "herramientas/realesrgan-ncnn-vulkan/realesrgan-ncnn-vulkan.exe",
  "modelo": "realesrgan-x4plus",
  "escala": 2,
  "tile": 0,
  "gpu_id": "auto"
}
```

El campo `habilitado` se conserva para el procesador independiente; el perfil Ultra lo activa de forma controlada. El modelo general es apropiado para fotografia. La escala aumenta mucho el tiempo, VRAM, almacenamiento y resolucion. `tile: 0` deja la seleccion automatica; si falta memoria, prueba 128 o 64. Si el ejecutable falla o no existe, la captura original sigue intacta y el fallback crea Alta calidad desde los originales.

El proyecto oficial documenta que el binario portable incluye modelos y funciona con GPU Intel, AMD o NVIDIA mediante NCNN/Vulkan: [Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN#portable-executable-files-ncnn) y [Real-ESRGAN NCNN Vulkan](https://github.com/xinntao/Real-ESRGAN-ncnn-vulkan).

## Pruebas

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

Las pruebas generan imagenes sinteticas, verifican que los originales y videos previos no cambien, validan carpetas versionadas, fallback de IA, duracion y recuento exacto de fotogramas a 30/60 FPS, y generan/inspeccionan ambos MP4 con ffprobe. No se conectan a la camara ni a Moonraker.

Consulta [la arquitectura](docs/ARQUITECTURA.md) y [la validacion](docs/VALIDACION.md) para mas detalle.
