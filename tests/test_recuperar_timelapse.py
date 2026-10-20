import hashlib
import json
import shutil

import cv2
import numpy as np
import pytest

from app import recuperar_timelapse


pytestmark = pytest.mark.skipif(
    not shutil.which("ffmpeg"), reason="FFmpeg no esta disponible"
)


def test_recupera_dos_videos_sin_modificar_jpg(tmp_path, monkeypatch):
    sesion = tmp_path / "sesion"
    sesion.mkdir()
    fotos = []
    for indice in range(3):
        ruta = sesion / f"capa_{indice + 1:06d}.jpg"
        imagen = np.full((90, 160, 3), 50 + indice * 20, dtype=np.uint8)
        assert cv2.imwrite(str(ruta), imagen)
        fotos.append(ruta)
    hashes = [hashlib.sha256(ruta.read_bytes()).hexdigest() for ruta in fotos]

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "config.json").write_text(
        json.dumps({
            "video": {
                "ancho_horizontal": 426, "alto_horizontal": 240,
                "ancho_vertical": 240, "alto_vertical": 426,
                "preset": "ultrafast", "crf": 24,
            }
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(recuperar_timelapse, "ROOT", tmp_path)

    recuperar_timelapse.recuperar(sesion, 3.0, 12)

    assert (sesion / "timelapse_horizontal.mp4").stat().st_size > 0
    assert (sesion / "timelapse_tiktok_9x16.mp4").stat().st_size > 0
    assert [hashlib.sha256(ruta.read_bytes()).hexdigest() for ruta in fotos] == hashes
