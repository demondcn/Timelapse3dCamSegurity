# Validacion de la mejora de calidad

## Pruebas automatizadas

La suite no necesita red, camara ni impresora. Cubre:

- preservacion byte a byte de los JPG originales mediante SHA-256;
- reduccion de variacion de luminancia en una secuencia con parpadeo sintetico;
- limites y rechazo de configuraciones agresivas o invalidas;
- ejecucion sin Real-ESRGAN cuando esta desactivado;
- generacion real con FFmpeg e inspeccion con ffprobe de codec, formato y dimensiones.

Resultado de referencia en Windows, Python 3.13, OpenCV 5.0 y FFmpeg 9.0:

```text
8 passed
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

## Criterio visual recomendado

Antes de adoptar parametros mas fuertes, compara los mismos detalles finos en las dos carpetas: texto de la cama, aristas de la pieza, reflejos del filamento y grano del fondo. Sube `nitidez` en pasos de 0.05 y evita halos blancos. Si la superficie parece plastificada, baja `reduccion_ruido`. Para una escena estable no amplíes los limites de ganancia salvo que las mediciones muestren parpadeo residual.
