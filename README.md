# Timelapse Tapo C210 + Creality Hi

Captura una fotografia por cada evento nuevo `capture 0` de Moonraker y, cuando termina la impresion, crea dos videos:

- `timelapse_horizontal.mp4`: 1920 x 1080.
- `timelapse_tiktok_9x16.mp4`: 1080 x 1920.

El programa solamente lee Moonraker. No mueve el cabezal, no controla la impresora y no envia G-code.

## Instalacion

Requisitos: Windows, Python 3.10 o posterior, FFmpeg en `PATH`, y acceso local a la impresora y la camara.

```powershell
py -m pip install -r requirements.txt
winget install --id Gyan.FFmpeg -e
```

Despues de instalar FFmpeg, cierra y vuelve a abrir la consola.

Copia `config/config.example.json` como `config/config.json` y completa las direcciones y credenciales locales.

## Organizacion del proyecto

```text
tapo_auto_work/
  5_TIMELAPSE_AUTOMATICO.bat    inicio normal
  3_RECUPERAR_MP4.bat           recuperacion de una sesion
  README.md                     documentacion principal
  requirements.txt             dependencias de uso
  requirements-dev.txt         dependencias de pruebas
  app/                          codigo Python de la aplicacion
    __init__.py
    timelapse_fluidd.py
    exportador_video.py
    recuperar_timelapse.py
  config/                       configuracion
    config.example.json
    config.json
  docs/                         documentacion tecnica adicional
  tests/                        pruebas automatizadas
  resultados/                   fotos y videos generados
```

## Uso normal

1. Inicia la impresion con el modo Smooth y los eventos `capture 0`.
2. Ejecuta `5_TIMELAPSE_AUTOMATICO.bat`.
3. Deja la ventana abierta mientras se recopilan las fotos.
4. Cuando Moonraker informa que la impresion termino, el programa genera los dos MP4.
5. Espera hasta que aparezca el mensaje `RESULTADOS EN`.

El MP4 final se crea al terminar la impresion, no durante la recopilacion. Para finalizar antes, pulsa `Ctrl+C` una vez y espera la exportacion.

No cierres la ventana con la X: Windows puede terminar Python sin darle tiempo a crear el video. El archivo `5_TIMELAPSE_AUTOMATICO.bat` no aplica mejoras, IA ni perfiles adicionales.

## Recuperar una sesion

Usa `3_RECUPERAR_MP4.bat` si quedaron los JPG pero faltan los MP4.

- Si lo ejecutas normalmente, recupera la sesion mas reciente.
- Si arrastras una carpeta de sesion encima del BAT, recupera esa carpeta.
- Los JPG originales no se modifican.

## Arquitectura

El sistema separa la captura, la exportacion y la recuperacion:

```text
Tapo C210 --RTSP--> hilo Camera --------> ultimo fotograma disponible
                                                |
Moonraker --WebSocket--> evento capture 0 --> espera configurada
                                                |
                                                v
                                       capa_NNNNNN.jpg
                                                |
                             impresion terminada o Ctrl+C
                                                |
                                                v
                                   app/exportador_video.py
                                         /            \
                                        v              v
                         timelapse_horizontal.mp4   timelapse_tiktok_9x16.mp4
```

Durante la impresion ocurren estas tareas:

1. `Camera` mantiene abierto el stream RTSP y conserva el fotograma mas reciente.
2. `PrinterEvents` escucha por WebSocket solamente eventos nuevos `capture 0`.
3. Cada evento se coloca en una cola y se programa usando `retardo_captura_seg`.
4. El fotograma se guarda como `capa_000001.jpg`, `capa_000002.jpg`, etc.
5. El programa consulta el estado de impresion cada tres segundos.
6. Cuando recibe `complete`, `cancelled`, `error` o `standby`, cierra la captura y exporta los videos.
7. Si se pulsa `Ctrl+C`, realiza el mismo cierre y exporta las fotos recopiladas hasta ese momento.

Opcionalmente, otro proceso FFmpeg copia el stream RTSP a `video_completo.mkv`. Esta grabacion es independiente del timelapse por capas y puede no existir si la camara rechaza una segunda conexion RTSP.

## Que hace cada archivo Python

### `app/timelapse_fluidd.py`

Es el programa principal que ejecuta el BAT numero 5.

Responsabilidades:

- Cargar `config/config.json`.
- Conectarse a la Tapo por RTSP.
- Escuchar Moonraker por WebSocket.
- Detectar los eventos `capture 0`.
- Guardar una fotografia por capa.
- Detectar el final de la impresion.
- Solicitar a `app/exportador_video.py` la creacion de los dos MP4.
- Intentar grabar `video_completo.mkv` cuando esa opcion esta activa.

### `app/exportador_video.py`

Es el modulo compartido que sabe convertir una secuencia de JPG en video.

Responsabilidades:

- Validar codec, calidad, dimensiones y FPS.
- Crear el manifiesto temporal que FFmpeg usa para leer las fotos en orden.
- Mantener la duracion definida por `fotos_por_segundo`.
- Recortar y escalar las imagenes para horizontal y vertical.
- Codificar H.264/H.265 y usar archivos temporales para no dejar un MP4 incompleto.

No se ejecuta directamente. Lo utilizan tanto `app/timelapse_fluidd.py` como `app/recuperar_timelapse.py`.

### `app/recuperar_timelapse.py`

Es la herramienta de emergencia que ejecuta el BAT numero 3.

No se conecta a Moonraker ni a la camara. Busca los archivos `capa_*.jpg` de una sesion y vuelve a llamar a `app/exportador_video.py`. Existe separado del programa principal porque permite reconstruir videos despues de cerrar accidentalmente la ventana, reiniciar el PC o sufrir un fallo de exportacion sin repetir la impresion.

## Por que existen dos archivos de configuracion

### `config/config.example.json`

Es una plantilla publica y segura:

- Contiene todas las opciones disponibles.
- Usa direcciones y credenciales ficticias.
- Puede guardarse en Git y compartirse.
- Sirve para crear una configuracion nueva.

### `config/config.json`

Es la configuracion real que utiliza el programa:

- Contiene la IP real de la impresora y la camara.
- Contiene el usuario y la contrasena de la Tapo.
- Puede tener ajustes propios de video y captura.
- Esta ignorado por Git para evitar publicar credenciales.

No son dos configuraciones activas: el programa solamente lee `config/config.json`. El archivo `config/config.example.json` es una plantilla y documentacion de referencia.

## Por que existen dos archivos de requisitos

### `requirements.txt`

Contiene solo las dependencias necesarias para utilizar el programa:

- `opencv-python`: lectura RTSP, manejo y guardado de imagenes.
- `websocket-client`: conexion con los eventos de Moonraker.

Instalacion:

```powershell
py -m pip install -r requirements.txt
```

### `requirements-dev.txt`

Contiene las dependencias para desarrollar y ejecutar pruebas. Su primera linea incluye automaticamente todo `requirements.txt`, y ademas instala `pytest`.

```text
-r requirements.txt
pytest>=8,<10
```

Un usuario normal solo necesita `requirements.txt`. `requirements-dev.txt` se utiliza al modificar o verificar el codigo.

## Configuracion relevante

- `retardo_captura_seg`: espera entre `capture 0` y la fotografia.
- `fotos_por_segundo`: velocidad narrativa del timelapse.
- `fps_timelapse`: FPS del archivo MP4.
- `grabar_video_completo`: activa o desactiva la copia continua RTSP.
- `video.crf`: calidad de compresion; un numero menor produce mayor calidad y archivos mas grandes.
- `video.preset`: equilibrio entre velocidad y compresion.
- `video.codec`: `libx264` o `libx265`.
- `video.ancho_*` y `video.alto_*`: dimensiones horizontal y vertical.

## Archivos de una sesion

```text
resultados/AAAA-MM-DD_HH-MM-SS_TIMELAPSE/
  capa_000001.jpg
  capa_000002.jpg
  ...
  timelapse_horizontal.mp4
  timelapse_tiktok_9x16.mp4
  video_completo.mkv
```

Los JPG son la fuente recuperable y no se eliminan al exportar.

## Seguridad

- No publiques `config/config.json`.
- No abras los puertos 554 o 7125 hacia Internet.
- Mantén la impresora, la camara y el PC en la misma red local.
- Si una credencial se comparte accidentalmente, cambiala en la Tapo y actualiza `config/config.json`.

## Pruebas

```powershell
py -m pip install -r requirements-dev.txt
py -m pytest -q
```

Las pruebas generan imagenes sinteticas. No se conectan a la impresora, Moonraker ni la camara.
