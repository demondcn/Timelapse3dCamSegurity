"""Mejora no destructiva y temporalmente estable de fotografias de timelapse."""

from __future__ import annotations

import json
import math
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence

import cv2
import numpy as np


@dataclass(frozen=True)
class RealESRGANConfig:
    habilitado: bool = False
    ejecutable: str = "herramientas/realesrgan-ncnn-vulkan/realesrgan-ncnn-vulkan.exe"
    modelo: str = "realesrgan-x4plus"
    escala: int = 2
    tile: int = 0
    gpu_id: str = "auto"


@dataclass(frozen=True)
class MejoraConfig:
    habilitada: bool = True
    reduccion_ruido: float = 3.0
    exposicion_ev: float = 0.0
    estabilizar_exposicion: bool = True
    ganancia_minima: float = 0.9
    ganancia_maxima: float = 1.1
    suavizado_temporal: float = 0.85
    cambio_maximo_por_fotograma: float = 0.015
    contraste: float = 1.05
    nitidez: float = 0.35
    radio_nitidez: float = 1.2
    calidad_jpg: int = 95
    real_esrgan: RealESRGANConfig = RealESRGANConfig()


def _numero(datos: Mapping[str, object], clave: str, predeterminado: float) -> float:
    valor = datos.get(clave, predeterminado)
    if isinstance(valor, bool):
        raise ValueError(f"mejora.{clave} debe ser numerico")
    try:
        resultado = float(valor)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"mejora.{clave} debe ser numerico") from exc
    if not math.isfinite(resultado):
        raise ValueError(f"mejora.{clave} debe ser finito")
    return resultado


def cargar_configuracion(datos: Mapping[str, object] | None) -> MejoraConfig:
    """Construye y valida la configuracion sin depender de ``config.json``."""
    datos = datos or {}
    sr_datos = datos.get("real_esrgan", {})
    if not isinstance(sr_datos, Mapping):
        raise ValueError("mejora.real_esrgan debe ser un objeto JSON")
    sr = RealESRGANConfig(
        habilitado=bool(sr_datos.get("habilitado", False)),
        ejecutable=str(sr_datos.get("ejecutable", RealESRGANConfig.ejecutable)),
        modelo=str(sr_datos.get("modelo", RealESRGANConfig.modelo)),
        escala=int(_numero(sr_datos, "escala", 2)),
        tile=int(_numero(sr_datos, "tile", 0)),
        gpu_id=str(sr_datos.get("gpu_id", "auto")),
    )
    config = MejoraConfig(
        habilitada=bool(datos.get("habilitada", True)),
        reduccion_ruido=_numero(datos, "reduccion_ruido", 3.0),
        exposicion_ev=_numero(datos, "exposicion_ev", 0.0),
        estabilizar_exposicion=bool(datos.get("estabilizar_exposicion", True)),
        ganancia_minima=_numero(datos, "ganancia_minima", 0.9),
        ganancia_maxima=_numero(datos, "ganancia_maxima", 1.1),
        suavizado_temporal=_numero(datos, "suavizado_temporal", 0.85),
        cambio_maximo_por_fotograma=_numero(datos, "cambio_maximo_por_fotograma", 0.015),
        contraste=_numero(datos, "contraste", 1.05),
        nitidez=_numero(datos, "nitidez", 0.35),
        radio_nitidez=_numero(datos, "radio_nitidez", 1.2),
        calidad_jpg=int(_numero(datos, "calidad_jpg", 95)),
        real_esrgan=sr,
    )
    if not 0 <= config.reduccion_ruido <= 12:
        raise ValueError("mejora.reduccion_ruido debe estar entre 0 y 12")
    if not -1.0 <= config.exposicion_ev <= 1.0:
        raise ValueError("mejora.exposicion_ev debe estar entre -1 y 1 EV")
    if not 0.5 <= config.ganancia_minima <= 1.5:
        raise ValueError("mejora.ganancia_minima debe estar entre 0.5 y 1.5")
    if not config.ganancia_minima <= config.ganancia_maxima <= 2.0:
        raise ValueError("mejora.ganancia_maxima debe ser >= ganancia_minima y <= 2")
    if not 0 <= config.suavizado_temporal <= 1:
        raise ValueError("mejora.suavizado_temporal debe estar entre 0 y 1")
    if not 0 <= config.cambio_maximo_por_fotograma <= 0.25:
        raise ValueError("mejora.cambio_maximo_por_fotograma debe estar entre 0 y 0.25")
    if not 0.75 <= config.contraste <= 1.35:
        raise ValueError("mejora.contraste debe estar entre 0.75 y 1.35")
    if not 0 <= config.nitidez <= 1.5 or not 0.3 <= config.radio_nitidez <= 5:
        raise ValueError("Parametros de nitidez fuera de rango")
    if not 80 <= config.calidad_jpg <= 100:
        raise ValueError("mejora.calidad_jpg debe estar entre 80 y 100")
    if sr.escala not in {2, 3, 4} or sr.tile < 0:
        raise ValueError("Real-ESRGAN requiere escala 2, 3 o 4 y tile >= 0")
    return config


def listar_originales(carpeta: Path) -> list[Path]:
    return sorted(p for p in Path(carpeta).glob("capa_*.jpg") if p.is_file())


def _luminancia_robusta(imagen: np.ndarray) -> float:
    alto, ancho = imagen.shape[:2]
    factor = min(1.0, 320.0 / max(alto, ancho))
    if factor < 1:
        imagen = cv2.resize(imagen, None, fx=factor, fy=factor, interpolation=cv2.INTER_AREA)
    gris = cv2.cvtColor(imagen, cv2.COLOR_BGR2GRAY)
    # La mediana resiste reflejos puntuales, LEDs y la boquilla brillante.
    return float(np.median(gris))


def _suavizar_referencia(valores: Sequence[float], peso_global: float, cambio_maximo: float) -> np.ndarray:
    serie = np.asarray(valores, dtype=np.float64)
    referencia_global = float(np.median(serie))
    if len(serie) == 1:
        return np.asarray([referencia_global])

    # Dos pasadas eliminan el desfase temporal de un EMA de una sola direccion.
    alpha = 0.65
    ida = serie.copy()
    vuelta = serie.copy()
    for indice in range(1, len(serie)):
        ida[indice] = alpha * ida[indice - 1] + (1 - alpha) * serie[indice]
    for indice in range(len(serie) - 2, -1, -1):
        vuelta[indice] = alpha * vuelta[indice + 1] + (1 - alpha) * serie[indice]
    local = (ida + vuelta) / 2.0
    referencia = peso_global * referencia_global + (1 - peso_global) * local

    if cambio_maximo > 0:
        limite = cambio_maximo * 255.0
        for indice in range(1, len(referencia)):
            referencia[indice] = np.clip(
                referencia[indice], referencia[indice - 1] - limite, referencia[indice - 1] + limite
            )
    return referencia


def calcular_ganancias(
    luminancias: Sequence[float], config: MejoraConfig
) -> tuple[np.ndarray, np.ndarray]:
    if not luminancias:
        raise ValueError("No hay luminancias para analizar")
    valores = np.maximum(np.asarray(luminancias, dtype=np.float64), 1.0)
    if config.estabilizar_exposicion:
        referencia = _suavizar_referencia(
            valores, config.suavizado_temporal, config.cambio_maximo_por_fotograma
        )
        ganancias = referencia / valores
    else:
        referencia = valores.copy()
        ganancias = np.ones_like(valores)
    ganancias *= 2.0 ** config.exposicion_ev
    ganancias = np.clip(ganancias, config.ganancia_minima, config.ganancia_maxima)
    return ganancias, referencia


def mejorar_fotograma(imagen: np.ndarray, ganancia: float, config: MejoraConfig) -> np.ndarray:
    if imagen is None or imagen.ndim != 3 or imagen.shape[2] != 3:
        raise ValueError("La imagen debe ser BGR de tres canales")
    if config.reduccion_ruido > 0:
        imagen = cv2.fastNlMeansDenoisingColored(
            imagen, None, config.reduccion_ruido, config.reduccion_ruido, 7, 21
        )

    # Exposicion y contraste se aplican solo a L para no hacer oscilar el color.
    lab = cv2.cvtColor(imagen, cv2.COLOR_BGR2LAB)
    luz = lab[:, :, 0].astype(np.float32)
    luz = (luz * float(ganancia) - 127.5) * config.contraste + 127.5
    lab[:, :, 0] = np.clip(luz, 0, 255).astype(np.uint8)
    resultado = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)

    if config.nitidez > 0:
        desenfoque = cv2.GaussianBlur(resultado, (0, 0), config.radio_nitidez)
        resultado = cv2.addWeighted(
            resultado, 1.0 + config.nitidez, desenfoque, -config.nitidez, 0
        )
    return resultado


def _resolver_ejecutable(ruta: str, base: Path) -> Path:
    ejecutable = Path(ruta).expanduser()
    if not ejecutable.is_absolute():
        ejecutable = base / ejecutable
    return ejecutable.resolve()


def _aplicar_real_esrgan(
    imagen: np.ndarray, destino: Path, config: MejoraConfig, base: Path
) -> np.ndarray:
    sr = config.real_esrgan
    ejecutable = _resolver_ejecutable(sr.ejecutable, base)
    if not ejecutable.is_file():
        raise FileNotFoundError(
            "Real-ESRGAN esta habilitado pero no existe el ejecutable configurado: "
            f"{ejecutable}"
        )
    with tempfile.TemporaryDirectory(prefix="tapo_esrgan_", dir=destino.parent) as temporal:
        temporal = Path(temporal)
        entrada = temporal / "entrada.png"
        salida = temporal / "salida.png"
        if not cv2.imwrite(str(entrada), imagen):
            raise RuntimeError("No se pudo preparar la entrada temporal de Real-ESRGAN")
        comando = [
            str(ejecutable), "-i", str(entrada), "-o", str(salida),
            "-n", sr.modelo, "-s", str(sr.escala), "-t", str(sr.tile), "-f", "png",
        ]
        if sr.gpu_id.lower() != "auto":
            comando.extend(["-g", sr.gpu_id])
        proceso = subprocess.run(
            comando, cwd=ejecutable.parent, capture_output=True, text=True, timeout=900
        )
        if proceso.returncode != 0 or not salida.is_file():
            detalle = (proceso.stderr or proceso.stdout)[-1200:]
            raise RuntimeError(f"Real-ESRGAN fallo (codigo {proceso.returncode}): {detalle}")
        resultado = cv2.imread(str(salida), cv2.IMREAD_COLOR)
        if resultado is None:
            raise RuntimeError("Real-ESRGAN no produjo una imagen legible")
        return resultado


def procesar_secuencia(
    originales: Iterable[Path],
    carpeta_salida: Path,
    config: MejoraConfig,
    *,
    base: Path | None = None,
    progreso: Callable[[str], None] | None = None,
) -> list[Path]:
    """Procesa una secuencia conservando los archivos de entrada sin cambios."""
    archivos = [Path(p).resolve() for p in originales]
    if not archivos:
        raise ValueError("No se encontraron fotografias capa_*.jpg")
    salida = Path(carpeta_salida).resolve()
    if salida in archivos or any(p.parent == salida for p in archivos):
        raise ValueError("La carpeta de salida debe ser distinta de la carpeta de originales")
    salida.mkdir(parents=True, exist_ok=True)
    base = (base or Path(__file__).resolve().parent).resolve()

    luminancias: list[float] = []
    for archivo in archivos:
        imagen = cv2.imread(str(archivo), cv2.IMREAD_COLOR)
        if imagen is None:
            raise RuntimeError(f"No se pudo leer la fotografia: {archivo.name}")
        luminancias.append(_luminancia_robusta(imagen))
    ganancias, referencias = calcular_ganancias(luminancias, config)

    resultados: list[Path] = []
    total = len(archivos)
    for indice, (archivo, ganancia) in enumerate(zip(archivos, ganancias), start=1):
        imagen = cv2.imread(str(archivo), cv2.IMREAD_COLOR)
        mejorada = mejorar_fotograma(imagen, float(ganancia), config)
        destino = salida / archivo.name
        if config.real_esrgan.habilitado:
            mejorada = _aplicar_real_esrgan(mejorada, destino, config, base)
        temporal = destino.with_name(f".{destino.stem}.tmp.jpg")
        ok = cv2.imwrite(
            str(temporal), mejorada, [cv2.IMWRITE_JPEG_QUALITY, config.calidad_jpg]
        )
        if not ok:
            raise RuntimeError(f"No se pudo escribir la fotografia mejorada: {destino.name}")
        temporal.replace(destino)
        resultados.append(destino)
        if progreso and (indice == total or indice == 1 or indice % 10 == 0):
            progreso(f"Mejora de fotografias: {indice}/{total}")

    informe = {
        "version": 1,
        "fotografias": total,
        "configuracion": asdict(config),
        "luminancia_original": [round(x, 3) for x in luminancias],
        "luminancia_referencia": [round(float(x), 3) for x in referencias],
        "ganancias": [round(float(x), 6) for x in ganancias],
    }
    (salida / "informe_mejora.json").write_text(
        json.dumps(informe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return resultados
