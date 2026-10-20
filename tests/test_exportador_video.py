import json
import shutil
import subprocess
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.exportador_video import cargar_configuracion, exportar_videos


pytestmark = pytest.mark.skipif(
    not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
    reason="FFmpeg/ffprobe no estan disponibles",
)


def _secuencia(carpeta: Path) -> list[Path]:
    carpeta.mkdir()
    rutas = []
    for indice in range(1, 5):
        imagen = np.zeros((180, 320, 3), dtype=np.uint8)
        imagen[:] = (30 + indice * 10, 60, 100)
        cv2.circle(imagen, (50 * indice, 90), 25, (220, 180, 40), -1)
        ruta = carpeta / f"capa_{indice:06d}.jpg"
        assert cv2.imwrite(str(ruta), imagen)
        rutas.append(ruta)
    return rutas


def _sondeo(ruta: Path) -> dict:
    proceso = subprocess.run(
        [
            shutil.which("ffprobe"), "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=codec_name,width,height,pix_fmt:format=duration",
            "-of", "json", str(ruta),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(proceso.stdout)


def test_exporta_h264_horizontal_y_vertical(tmp_path):
    fotos = _secuencia(tmp_path / "fotos")
    config = cargar_configuracion(
        {
            "crf": 22,
            "preset": "ultrafast",
            "ancho_horizontal": 640,
            "alto_horizontal": 360,
            "ancho_vertical": 360,
            "alto_vertical": 640,
        }
    )
    salidas = exportar_videos(fotos, tmp_path / "videos", 4.0, 12, config)

    assert [ruta.name for ruta in salidas] == [
        "timelapse_horizontal.mp4",
        "timelapse_tiktok_9x16.mp4",
    ]
    horizontal, vertical = (_sondeo(ruta) for ruta in salidas)
    stream_h = horizontal["streams"][0]
    stream_v = vertical["streams"][0]
    assert (stream_h["width"], stream_h["height"]) == (640, 360)
    assert (stream_v["width"], stream_v["height"]) == (360, 640)
    assert stream_h["codec_name"] == stream_v["codec_name"] == "h264"
    assert stream_h["pix_fmt"] == stream_v["pix_fmt"] == "yuv420p"
    assert 0.7 <= float(horizontal["format"]["duration"]) <= 1.5
