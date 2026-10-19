"""Exportacion de secuencias JPG a MP4 horizontal y vertical mediante FFmpeg."""

from __future__ import annotations

import math
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence


@dataclass(frozen=True)
class VideoConfig:
    crf: int = 18
    preset: str = "slow"
    codec: str = "libx264"
    pix_fmt: str = "yuv420p"
    ancho_horizontal: int = 1920
    alto_horizontal: int = 1080
    ancho_vertical: int = 1080
    alto_vertical: int = 1920


def cargar_configuracion(datos: Mapping[str, object] | None) -> VideoConfig:
    datos = datos or {}
    try:
        config = VideoConfig(
            crf=int(datos.get("crf", 18)),
            preset=str(datos.get("preset", "slow")),
            codec=str(datos.get("codec", "libx264")),
            pix_fmt=str(datos.get("pix_fmt", "yuv420p")),
            ancho_horizontal=int(datos.get("ancho_horizontal", 1920)),
            alto_horizontal=int(datos.get("alto_horizontal", 1080)),
            ancho_vertical=int(datos.get("ancho_vertical", 1080)),
            alto_vertical=int(datos.get("alto_vertical", 1920)),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("La configuracion de video contiene valores no validos") from exc
    if not 0 <= config.crf <= 35:
        raise ValueError("video.crf debe estar entre 0 y 35")
    if config.preset not in {"ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"}:
        raise ValueError("video.preset no es un preset FFmpeg permitido")
    if config.codec not in {"libx264", "libx265"}:
        raise ValueError("video.codec debe ser libx264 o libx265")
    if config.pix_fmt not in {"yuv420p", "yuv420p10le"}:
        raise ValueError("video.pix_fmt debe ser yuv420p o yuv420p10le")
    dimensiones = (
        config.ancho_horizontal, config.alto_horizontal,
        config.ancho_vertical, config.alto_vertical,
    )
    if any(valor < 240 or valor > 7680 or valor % 2 for valor in dimensiones):
        raise ValueError("Las dimensiones de video deben ser pares y estar entre 240 y 7680")
    return config


def _ruta_concat(ruta: Path) -> str:
    return str(ruta.resolve()).replace("\\", "/").replace("'", "'\\''")


def _crear_manifiesto(archivos: Sequence[Path], duracion: float, destino: Path) -> None:
    lineas = ["ffconcat version 1.0"]
    for archivo in archivos:
        lineas.extend([f"file '{_ruta_concat(archivo)}'", f"duration {duracion:.12f}"])
    lineas.append(f"file '{_ruta_concat(archivos[-1])}'")
    destino.write_text("\n".join(lineas) + "\n", encoding="utf-8")


def _filtro(ancho: int, alto: int, fps: int, pix_fmt: str) -> str:
    return (
        f"scale={ancho}:{alto}:force_original_aspect_ratio=increase:"
        "in_range=full:out_range=tv:flags=lanczos,"
        f"crop={ancho}:{alto},setsar=1,fps={fps},format={pix_fmt}"
    )


def exportar_videos(
    archivos: Sequence[Path],
    carpeta_salida: Path,
    fotos_por_segundo: float,
    fps_salida: int,
    config: VideoConfig,
    *,
    progreso: Callable[[str], None] | None = None,
) -> list[Path]:
    if not archivos:
        raise ValueError("No hay fotografias para exportar")
    if not math.isfinite(fotos_por_segundo) or not 0.1 <= fotos_por_segundo <= 60:
        raise ValueError("fotos_por_segundo debe estar entre 0.1 y 60")
    if not 1 <= fps_salida <= 120:
        raise ValueError("fps_salida debe estar entre 1 y 120")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise FileNotFoundError("FFmpeg no esta instalado o no esta en PATH")
    archivos = [Path(p).resolve() for p in archivos]
    if any(not p.is_file() for p in archivos):
        raise FileNotFoundError("Falta una fotografia de la secuencia")
    carpeta_salida = Path(carpeta_salida).resolve()
    carpeta_salida.mkdir(parents=True, exist_ok=True)

    salidas: list[Path] = []
    with tempfile.TemporaryDirectory(prefix="tapo_ffmpeg_") as temporal:
        manifiesto = Path(temporal) / "fotogramas.ffconcat"
        _crear_manifiesto(archivos, 1.0 / fotos_por_segundo, manifiesto)
        trabajos = (
            ("timelapse_horizontal.mp4", config.ancho_horizontal, config.alto_horizontal),
            ("timelapse_tiktok_9x16.mp4", config.ancho_vertical, config.alto_vertical),
        )
        for nombre, ancho, alto in trabajos:
            destino = carpeta_salida / nombre
            temporal_mp4 = carpeta_salida / f".{Path(nombre).stem}.tmp.mp4"
            temporal_mp4.unlink(missing_ok=True)
            if progreso:
                progreso(f"Generando {nombre} con FFmpeg")
            comando = [
                ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                "-safe", "0", "-f", "concat", "-i", str(manifiesto),
                "-vf", _filtro(ancho, alto, fps_salida, config.pix_fmt),
                "-c:v", config.codec, "-crf", str(config.crf),
                "-preset", config.preset, "-pix_fmt", config.pix_fmt,
                "-color_primaries", "bt709", "-color_trc", "bt709",
                "-colorspace", "bt709", "-color_range", "tv", "-movflags", "+faststart",
                "-an", str(temporal_mp4),
            ]
            proceso = subprocess.run(comando, capture_output=True, text=True)
            if proceso.returncode != 0:
                temporal_mp4.unlink(missing_ok=True)
                raise RuntimeError(f"FFmpeg fallo creando {nombre}: {proceso.stderr[-1600:]}")
            temporal_mp4.replace(destino)
            salidas.append(destino)
    return salidas
