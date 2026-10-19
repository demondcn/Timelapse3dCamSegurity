import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import cv2
import numpy as np
import pytest

from perfiles_exportacion import cargar_configuracion, exportar_perfil


def _crear_originales(carpeta: Path, cantidad: int = 6) -> list[Path]:
    carpeta.mkdir()
    fotos = []
    for indice in range(cantidad):
        imagen = np.full((180, 320, 3), (45, 75 + indice, 115), dtype=np.uint8)
        cv2.rectangle(imagen, (50 + indice * 4, 40), (180, 155), (210, 130, 35), -1)
        ruta = carpeta / f"capa_{indice + 1:06d}.jpg"
        assert cv2.imwrite(str(ruta), imagen)
        fotos.append(ruta)
    return fotos


def _hashes(rutas: list[Path]) -> list[str]:
    return [hashlib.sha256(ruta.read_bytes()).hexdigest() for ruta in rutas]


def _sondeo(ruta: Path) -> dict:
    proceso = subprocess.run(
        [
            shutil.which("ffprobe"), "-v", "error", "-select_streams", "v:0",
            "-count_frames", "-show_entries",
            "stream=codec_name,width,height,r_frame_rate,nb_read_frames:format=duration",
            "-of", "json", str(ruta),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(proceso.stdout)


def _config(perfil: str) -> dict:
    return {
        "fotos_por_segundo": 6.0,
        "mejora": {
            "reduccion_ruido": 0,
            "contraste": 1.0,
            "nitidez": 0,
            "real_esrgan": {"ejecutable": "definitivamente_no_existe.exe"},
        },
        "exportacion": {
            "perfil": perfil,
            "fallback_ultra": "alta_calidad",
            "interpolacion_movimiento": False,
            "perfiles": {
                "estandar": {
                    "ancho_horizontal": 320, "alto_horizontal": 180,
                    "ancho_vertical": 180, "alto_vertical": 320,
                },
                "alta_calidad": {
                    "ancho_horizontal": 320, "alto_horizontal": 180,
                    "ancho_vertical": 180, "alto_vertical": 320,
                    "preset": "ultrafast", "crf": 24,
                },
                "ultra_ia": {
                    "ancho_horizontal": 320, "alto_horizontal": 180,
                    "ancho_vertical": 180, "alto_vertical": 320,
                    "preset": "ultrafast", "crf": 24,
                },
            },
        },
    }


def test_valores_iniciales_de_los_tres_perfiles():
    config = cargar_configuracion({})
    assert config.perfil == "ultra_ia"
    assert config.perfiles["estandar"].backend == "opencv"
    assert config.perfiles["estandar"].fps == 30
    assert (config.perfiles["estandar"].ancho_horizontal, config.perfiles["estandar"].alto_horizontal) == (1920, 1080)
    assert config.perfiles["alta_calidad"].fps == 60
    assert (config.perfiles["alta_calidad"].ancho_vertical, config.perfiles["alta_calidad"].alto_vertical) == (2160, 3840)
    assert config.perfiles["ultra_ia"].real_esrgan is True


@pytest.mark.skipif(not shutil.which("ffprobe"), reason="ffprobe no disponible")
def test_estandar_opencv_conserva_duracion_y_archivos(tmp_path):
    sesion = tmp_path / "sesion"
    originales = _crear_originales(sesion)
    hashes = _hashes(originales)
    previo = sesion / "timelapse_existente.mp4"
    previo.write_bytes(b"video anterior que no debe cambiar")

    resultado = exportar_perfil(originales, sesion, _config("estandar"))

    assert resultado.perfil_efectivo == "estandar"
    assert resultado.directorio.name == "estandar"
    assert previo.read_bytes() == b"video anterior que no debe cambiar"
    assert _hashes(originales) == hashes
    for video in resultado.videos:
        datos = _sondeo(video)
        stream = datos["streams"][0]
        assert stream["codec_name"] == "mpeg4"
        assert stream["r_frame_rate"] == "30/1"
        assert int(stream["nb_read_frames"]) == 30
        assert float(datos["format"]["duration"]) == pytest.approx(1.0, abs=0.04)

    segundo = exportar_perfil(originales, sesion, _config("estandar"))
    assert segundo.directorio.name == "estandar_002"
    assert resultado.videos[0].is_file()


@pytest.mark.skipif(
    not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
    reason="FFmpeg/ffprobe no disponibles",
)
def test_alta_calidad_60_fps_duplica_sin_cambiar_duracion(tmp_path):
    sesion = tmp_path / "sesion"
    originales = _crear_originales(sesion)
    resultado = exportar_perfil(originales, sesion, _config("alta_calidad"))

    for video in resultado.videos:
        datos = _sondeo(video)
        stream = datos["streams"][0]
        assert stream["codec_name"] == "h264"
        assert stream["r_frame_rate"] == "60/1"
        assert int(stream["nb_read_frames"]) == 60
        assert float(datos["format"]["duration"]) == pytest.approx(1.0, abs=0.02)


@pytest.mark.skipif(
    not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
    reason="FFmpeg/ffprobe no disponibles",
)
def test_ultra_ia_ausente_hace_fallback_sobre_copias(tmp_path):
    sesion = tmp_path / "sesion"
    originales = _crear_originales(sesion)
    hashes = _hashes(originales)

    resultado = exportar_perfil(originales, sesion, _config("ultra_ia"))

    assert resultado.perfil_solicitado == "ultra_ia"
    assert resultado.perfil_efectivo == "alta_calidad"
    assert resultado.motivo_fallback
    assert _hashes(originales) == hashes
    fallido = sesion / "exportaciones" / "ultra_ia" / "informe_exportacion.json"
    assert json.loads(fallido.read_text(encoding="utf-8"))["estado"] == "fallido"
    informe = json.loads(
        (resultado.directorio / "informe_exportacion.json").read_text(encoding="utf-8")
    )
    assert informe["interpolacion_movimiento"] is False
    assert informe["duplicacion_fotogramas"] is True
