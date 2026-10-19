"""Timelapse Tapo C210 + Creality Hi. Solo LECTURA en Moonraker, no envia G-code."""
import argparse
import heapq
import json
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

try:
    import cv2
    import websocket
except ImportError as exc:
    raise SystemExit("Dependencia ausente: ejecuta 0_INSTALAR.bat primero") from exc

from exportador_video import cargar_configuracion as cargar_config_video
from exportador_video import exportar_videos
from mejora_imagenes import cargar_configuracion as cargar_config_mejora
from mejora_imagenes import procesar_secuencia

BASE = Path(__file__).resolve().parent
CFG = json.loads((BASE / "config.json").read_text(encoding="utf-8"))
PRINTER_HOST = CFG["impresora_ip"]
CAM_HOST = CFG["camara_ip"]
RTSP = (f"rtsp://{quote(CFG['usuario_camara'], safe='')}:"
        f"{quote(CFG['contrasena_camara'], safe='')}@{CAM_HOST}:554/stream1")
WS_URL = f"ws://{PRINTER_HOST}:7125/websocket"
STATE_URL = f"http://{PRINTER_HOST}:7125/printer/objects/query?print_stats"
# Evitar FPS=0 si la configuracion se modifica por error.
try:
    FPS = int(CFG.get("fps_timelapse", 30))
except (TypeError, ValueError):
    FPS = 30
if FPS <= 0 or FPS > 120:
    FPS = 30

# 6 fotos por segundo da un video util para TikTok (65 fotos -> 10.83 s),
# aunque el MP4 resultante se codifica a 30 FPS.
try:
    FOTO_FPS = float(CFG.get("fotos_por_segundo", 6.0))
except (TypeError, ValueError):
    FOTO_FPS = 6.0
if not 0.1 <= FOTO_FPS <= 60:
    FOTO_FPS = 6.0
CAPTURE_DELAY = float(CFG.get("retardo_captura_seg", 0.3))
TEST_OFFSETS = [float(x) for x in CFG.get("retardos_prueba_seg", [0, 0.3, 0.7, 1.1, 1.5, 2.0])]
EVENT_RE = re.compile(r"(?:^|\s)(?://\s*)?capture\s+0(?:\s|$)", re.I)


def tell(message):
    print(f"[{datetime.now():%H:%M:%S}] {message}", flush=True)


class Camera:
    def __init__(self):
        self.frame = None
        self.frame_at = 0.0
        self.lock = threading.Lock()
        self.alive = threading.Event()
        self.thread = None

    def start(self):
        self.alive.set()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def _loop(self):
        while self.alive.is_set():
            cap = cv2.VideoCapture(RTSP, cv2.CAP_FFMPEG)
            if not cap.isOpened():
                tell("No se puede abrir Tapo; reintentando en 3 s...")
                cap.release()
                time.sleep(3)
                continue
            tell("Tapo conectada: leyendo imagen en directo")
            try:
                while self.alive.is_set():
                    ok, frame = cap.read()
                    if not ok:
                        tell("Se perdio la transmision de Tapo; reconectando...")
                        break
                    with self.lock:
                        self.frame = frame
                        self.frame_at = time.monotonic()
            finally:
                cap.release()
            time.sleep(1)

    def latest(self):
        with self.lock:
            if self.frame is None:
                return None, None
            return self.frame.copy(), time.monotonic() - self.frame_at

    def stop(self):
        self.alive.clear()


class PrinterEvents:
    def __init__(self, output_queue):
        self.events = output_queue
        self.running = threading.Event()
        self.sock = None
        self.thread = None

    def start(self):
        self.running.set()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def _loop(self):
        def on_open(ws):
            tell("Moonraker conectado por WebSocket: escuchando nuevos 'capture 0'")

        def on_message(ws, raw):
            try:
                obj = json.loads(raw)
                if obj.get("method") != "notify_gcode_response":
                    return
                p = obj.get("params", [])
                msg = str(p[0]) if p else ""
                if EVENT_RE.search(msg.strip()):
                    self.events.put(time.monotonic())
            except Exception as exc:
                tell(f"Aviso procesando evento: {exc}")

        def on_error(ws, error):
            tell(f"Conexion Moonraker: {error}")

        while self.running.is_set():
            self.sock = websocket.WebSocketApp(
                WS_URL, on_open=on_open, on_message=on_message, on_error=on_error
            )
            self.sock.run_forever(ping_interval=20, ping_timeout=10)
            if self.running.is_set():
                tell("Reconectando Moonraker en 2 segundos...")
                time.sleep(2)

    def stop(self):
        self.running.clear()
        if self.sock is not None:
            self.sock.close()


def print_state():
    try:
        req = Request(STATE_URL, headers={"User-Agent": "TimelapseTapo/1.0"})
        with urlopen(req, timeout=2) as response:
            obj = json.load(response)
        return obj["result"]["status"]["print_stats"].get("state", "")
    except Exception:
        return None


def ffmpeg_record(folder):
    if not shutil.which("ffmpeg") or not CFG.get("grabar_video_completo", True):
        if CFG.get("grabar_video_completo", True):
            tell("FFmpeg no disponible: se guardaran fotos pero no video completo.")
        return None
    path = folder / "video_completo.mkv"
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error",
               "-rtsp_transport", "tcp", "-i", RTSP,
               "-map", "0:v:0", "-c:v", "copy", "-an", "-y", str(path)]
    try:
        proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
        tell(f"Video completo activado: {path.name}")
        return proc
    except OSError as exc:
        tell(f"No se pudo iniciar video completo: {exc}")
        return None


def stop_ffmpeg(proc):
    if not proc:
        return
    if proc.poll() is None:
        try:
            # La tecla q permite a FFmpeg cerrar el contenedor correctamente.
            proc.communicate(input=b"q\n", timeout=8)
        except (subprocess.TimeoutExpired, OSError):
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()


def build_video_opencv(files, target, vertical):
    size = (1080, 1920) if vertical else (1920, 1080)
    writer = cv2.VideoWriter(str(target), cv2.VideoWriter_fourcc(*"mp4v"), FPS, size)
    if not writer.isOpened():
        tell(f"No se pudo abrir el codificador para {target.name}")
        return
    try:
        for imgfile in files:
            frame = cv2.imread(str(imgfile))
            if frame is None:
                continue
            height, width = frame.shape[:2]
            if vertical:
                cropw = int(height * 9 / 16)
                cropw = min(cropw, width)
                left = (width - cropw) // 2
                frame = frame[:, left:left+cropw]
            out_frame = cv2.resize(frame, size, interpolation=cv2.INTER_AREA)
            for _ in range(max(1, round(FPS / FOTO_FPS))):
                writer.write(out_frame)
        tell(f"Creado: {target.name} (MP4V; FFmpeg permite H.264)")
    finally:
        writer.release()


def build_videos(folder, paths):
    if not paths:
        tell("No hay fotos para exportar. Revisa el modo Smooth y los mensajes capture 0.")
        return
    tell(f"Exportando {len(paths)} fotografias: {FOTO_FPS:g} fotos/s, MP4 a {FPS} fps...")
    if shutil.which("ffmpeg"):
        try:
            salidas = exportar_videos(
                paths, folder, FOTO_FPS, FPS, cargar_config_video(CFG.get("video")), progreso=tell
            )
            for salida in salidas:
                tell(f"Creado: {salida.name}")
        except (OSError, RuntimeError, ValueError) as exc:
            tell(f"ERROR exportando con FFmpeg: {exc}")
    else:
        build_video_opencv(paths, folder / "timelapse_horizontal.mp4", vertical=False)
        build_video_opencv(paths, folder / "timelapse_tiktok_9x16.mp4", vertical=True)


def run(mode):
    test = mode == "calibrar"
    base = BASE / "resultados"
    base.mkdir(exist_ok=True)
    folder = base / (datetime.now().strftime("%Y-%m-%d_%H-%M-%S") + ("_PRUEBA" if test else "_TIMELAPSE"))
    folder.mkdir()
    tell(f"Salida: {folder}")
    tell("Este programa SOLO LEE Moonraker; NO mueve el cabezal ni manda G-code.")
    tell("Los eventos del historial anterior no cuentan: solo escucha eventos NUEVOS.")
    tell("Puedes detener con Ctrl+C sin parar la impresion de la Creality Hi.")
    cam = Camera()
    cam.start()
    listener_queue = queue.Queue()
    listener = PrinterEvents(listener_queue)
    listener.start()
    recorder = None
    scheduled = []
    counter = 0
    event_count = 0
    last_event = -1000
    files = []
    first_printing = False
    check_time = 0
    try:
        start = time.monotonic()
        while True:
            if time.monotonic() - start > 30:
                raise RuntimeError("No llega imagen desde la Tapo. Comprueba Wi-Fi y credenciales.")
            frame, age = cam.latest()
            if frame is not None and age < 1:
                break
            time.sleep(.2)
        if not test:
            recorder = ffmpeg_record(folder)
        tell("ESCUCHANDO: espera a que la impresora genere 'capture 0'...")
        while True:
            now = time.monotonic()
            while True:
                try:
                    event_at = listener_queue.get_nowait()
                except queue.Empty:
                    break
                if event_at - last_event < 2:
                    continue
                last_event = event_at
                event_count += 1
                tell(f"Evento #{event_count}: capture 0")
                if test:
                    for offset in TEST_OFFSETS:
                        heapq.heappush(scheduled, (event_at + offset, event_count, offset))
                else:
                    heapq.heappush(scheduled, (event_at + CAPTURE_DELAY, event_count, CAPTURE_DELAY))

            while scheduled and scheduled[0][0] <= time.monotonic():
                _, num, offset = heapq.heappop(scheduled)
                frame, age = cam.latest()
                if frame is None or age is None or age > 0.8:
                    tell(f"Foto perdida: Tapo sin fotograma reciente ({num}, +{offset}s)")
                    continue
                if test:
                    path = folder / f"evento_{num:03d}_mas_{offset:.2f}s.jpg"
                else:
                    path = folder / f"capa_{len(files)+1:06d}.jpg"
                if cv2.imwrite(str(path), frame):
                    if not test:
                        files.append(path)
                    tell(f"Foto guardada: {path.name} (edad imagen {age:.2f} s)")
                else:
                    tell("ERROR guardando JPG")

            if test and event_count >= 3 and not scheduled:
                tell("Prueba terminada: revisa las fotos y elige el mejor retardo.")
                break

            if not test and time.monotonic() >= check_time:
                check_time = time.monotonic() + 3
                state = print_state()
                if state == "printing":
                    first_printing = True
                elif first_printing and state in {"complete", "cancelled", "error", "standby"}:
                    tell(f"Trabajo terminado (estado={state}). Exportando...")
                    break
            time.sleep(.025)
    except KeyboardInterrupt:
        tell("Detenido por el usuario. Guardando resultados...")
    finally:
        listener.stop()
        cam.stop()
        stop_ffmpeg(recorder)
        if not test:
            fotos_video = files
            if files:
                try:
                    config_mejora = cargar_config_mejora(CFG.get("mejora"))
                    if config_mejora.habilitada:
                        tell("Procesando copias mejoradas; los JPG originales no se modifican...")
                        fotos_video = procesar_secuencia(
                            files,
                            folder / "imagenes_mejoradas",
                            config_mejora,
                            base=BASE,
                            progreso=tell,
                        )
                except (OSError, RuntimeError, ValueError) as exc:
                    tell(f"AVISO: la mejora fallo; se exportaran los originales: {exc}")
                    fotos_video = files
            build_videos(folder, fotos_video)
        tell(f"RESULTADOS EN: {folder}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Timelapse Creality Hi + Tapo C210")
    parser.add_argument("modo", choices=("calibrar", "grabar"))
    opts = parser.parse_args()
    run(opts.modo)
