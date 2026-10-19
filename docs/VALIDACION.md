# Validacion de la mejora de calidad

## Pruebas automatizadas

La suite no necesita red, camara ni impresora. Cubre:

- preservacion byte a byte de los JPG originales mediante SHA-256;
- reduccion de variacion de luminancia en una secuencia con parpadeo sintetico;
- limites y rechazo de configuraciones agresivas o invalidas;
- ejecucion sin Real-ESRGAN cuando esta desactivado;
- fallback no destructivo cuando falta Real-ESRGAN;
- salidas versionadas que no reemplazan videos anteriores;
- generacion real con OpenCV y FFmpeg e inspeccion con ffprobe de codec, FPS, recuento, duracion y dimensiones.

Resultado de referencia en Windows, Python 3.13, OpenCV 5.0 y FFmpeg 9.0:

```text
13 passed
```

## Prueba con capturas reales

Se proceso una sesion existente de 65 fotografias Tapo de 2304 x 1296. La salida se escribio en una carpeta temporal distinta de la sesion.

| Comprobacion | Resultado |
|---|---:|
| Hash SHA-256 de los 65 originales antes/despues | Identico |
| Desviacion de mediana luminosa antes | 0.589 |
| Desviacion de mediana luminosa despues | 0.493 |
| Reduccion de variacion luminosa | 16.3 % |
| Fotografias mejoradas | 65/65 |

No se habilito Real-ESRGAN: esta validacion corresponde al camino obligatorio OpenCV.

`ffprobe` valido estas salidas:

| Salida | Resolucion | Codec/formato | Color | FPS | Duracion |
|---|---:|---|---|---:|---:|
| Horizontal | 1920 x 1080 | H.264 / yuv420p | BT.709, rango TV | 30 | 11.0 s |
| TikTok | 1080 x 1920 | H.264 / yuv420p | BT.709, rango TV | 30 | 11.0 s |

## Validacion de los tres perfiles

Se usaron seis capturas reales de 2304 x 1296 y `fotos_por_segundo = 6`, por lo que la duracion objetivo fue exactamente 1 segundo. La salida se escribio fuera de la sesion original.

| Perfil efectivo | Salida | Resolucion | FPS | Fotogramas | Duracion |
|---|---|---:|---:|---:|---:|
| Estandar/OpenCV | Horizontal | 1920 x 1080 | 30 | 30 | 1.000 s |
| Estandar/OpenCV | Vertical | 1080 x 1920 | 30 | 30 | 1.000 s |
| Alta calidad/FFmpeg | Horizontal | 3840 x 2160 | 60 | 60 | 1.000 s |
| Alta calidad/FFmpeg | Vertical | 2160 x 3840 | 60 | 60 | 1.000 s |

Ultra IA se solicito sin un ejecutable NCNN instalado. El sistema creo el informe de fallo y ejecuto Alta calidad como fallback desde los JPG originales. No trato los originales como destino y no uso interpolacion de movimiento.

La sesion existente de 266 fotografias se inventario antes y despues de la implementacion:

| Comprobacion | Antes | Despues |
|---|---:|---:|
| JPG originales | 266 | 266 |
| Archivos totales de la sesion | 537 | 537 |
| Bytes totales | 318922624 | 318922624 |
| Fingerprint agregado SHA-256 | `4b0a40e5...f2dec6` | `4b0a40e5...f2dec6` |

## Criterio visual recomendado

Antes de adoptar parametros mas fuertes, compara los mismos detalles finos en las dos carpetas: texto de la cama, aristas de la pieza, reflejos del filamento y grano del fondo. Sube `nitidez` en pasos de 0.05 y evita halos blancos. Si la superficie parece plastificada, baja `reduccion_ruido`. Para una escena estable no amplíes los limites de ganancia salvo que las mediciones muestren parpadeo residual.
