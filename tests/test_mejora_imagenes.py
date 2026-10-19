import hashlib
from pathlib import Path

import cv2
import numpy as np
import pytest

from mejora_imagenes import (
    calcular_ganancias,
    cargar_configuracion,
    procesar_secuencia,
)


def _hash(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def _crear_secuencia(carpeta: Path, niveles=(92, 108, 94, 110, 96, 107)) -> list[Path]:
    carpeta.mkdir()
    rng = np.random.default_rng(1234)
    rutas = []
    for indice, nivel in enumerate(niveles, start=1):
        imagen = np.full((180, 320, 3), (nivel - 8, nivel, nivel + 7), dtype=np.int16)
        ruido = rng.normal(0, 4, imagen.shape).astype(np.int16)
        imagen = np.clip(imagen + ruido, 0, 255).astype(np.uint8)
        cv2.rectangle(imagen, (80, 45), (240, 150), (45, 135, 205), -1)
        ruta = carpeta / f"capa_{indice:06d}.jpg"
        assert cv2.imwrite(str(ruta), imagen, [cv2.IMWRITE_JPEG_QUALITY, 96])
        rutas.append(ruta)
    return rutas


def _mediana_luma(ruta: Path) -> float:
    imagen = cv2.imread(str(ruta))
    return float(np.median(cv2.cvtColor(imagen, cv2.COLOR_BGR2GRAY)))


def test_procesamiento_preserva_originales_y_reduce_variacion(tmp_path):
    originales = _crear_secuencia(tmp_path / "originales")
    hashes = [_hash(ruta) for ruta in originales]
    config = cargar_configuracion(
        {
            "reduccion_ruido": 2,
            "contraste": 1.0,
            "nitidez": 0.2,
            "ganancia_minima": 0.8,
            "ganancia_maxima": 1.2,
            "suavizado_temporal": 0.95,
            "cambio_maximo_por_fotograma": 0.01,
            "calidad_jpg": 96,
        }
    )

    mejoradas = procesar_secuencia(originales, tmp_path / "mejoradas", config)

    assert len(mejoradas) == len(originales)
    assert hashes == [_hash(ruta) for ruta in originales]
    assert (tmp_path / "mejoradas" / "informe_mejora.json").is_file()
    antes = np.asarray([_mediana_luma(ruta) for ruta in originales])
    despues = np.asarray([_mediana_luma(ruta) for ruta in mejoradas])
    assert np.std(despues) < np.std(antes) * 0.45


def test_ganancias_limitadas_y_finitas():
    config = cargar_configuracion(
        {"ganancia_minima": 0.9, "ganancia_maxima": 1.1, "exposicion_ev": 0.1}
    )
    ganancias, referencias = calcular_ganancias([1, 80, 120, 250], config)
    assert np.all(np.isfinite(ganancias))
    assert np.all(np.isfinite(referencias))
    assert ganancias.min() >= 0.9
    assert ganancias.max() <= 1.1


@pytest.mark.parametrize(
    "datos",
    [
        {"contraste": 2},
        {"calidad_jpg": 20},
        {"ganancia_minima": 1.2, "ganancia_maxima": 1.0},
        {"real_esrgan": {"escala": 8}},
    ],
)
def test_rechaza_configuracion_peligrosa(datos):
    with pytest.raises(ValueError):
        cargar_configuracion(datos)


def test_real_esrgan_es_opcional(tmp_path):
    originales = _crear_secuencia(tmp_path / "originales", niveles=(100,))
    config = cargar_configuracion(
        {"real_esrgan": {"habilitado": False, "ejecutable": "no_existe.exe"}}
    )
    resultado = procesar_secuencia(originales, tmp_path / "mejoradas", config)
    assert resultado[0].is_file()


def test_real_esrgan_ausente_falla_sin_tocar_original(tmp_path):
    originales = _crear_secuencia(tmp_path / "originales", niveles=(100,))
    hash_antes = _hash(originales[0])
    config = cargar_configuracion(
        {"real_esrgan": {"habilitado": True, "ejecutable": "no_existe.exe"}}
    )
    with pytest.raises(FileNotFoundError, match="Real-ESRGAN"):
        procesar_secuencia(originales, tmp_path / "mejoradas", config)
    assert _hash(originales[0]) == hash_antes
