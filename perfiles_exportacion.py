"""Perfiles no destructivos de procesamiento y exportacion de timelapses."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Callable, Mapping, Sequence

import cv2

from exportador_video import VideoConfig, exportar_videos
from mejora_imagenes import (
    MejoraConfig,
    RealESRGANError,
    RealESRGANNoDisponibleError,
    cargar_configuracion as cargar_mejora,
    procesar_secuencia,
)


PERFIL_ESTANDAR = "estandar"
PERFIL_ALTA = "alta_calidad"
PERFIL_ULTRA = "ultra_ia"
PERFILES = (PERFIL_ESTANDAR, PERFIL_ALTA, PERFIL_ULTRA)


@dataclass(frozen=True)
class PerfilVideo:
    backend: str
    fps: int
    ancho_horizontal: int
    alto_horizontal: int
    ancho_vertical: int
    alto_vertical: int
    crf: int = 16
    preset: str = "slow"
    codec: str = "libx264"
    pix_fmt: str = "yuv420p"
    real_esrgan: bool = False


@dataclass(frozen=True)
class ConfigPerfiles:
    perfil: str
    fallback_ultra: str | None
    interpolacion_movimiento: bool
    perfiles: Mapping[str, PerfilVideo]


@dataclass(frozen=True)
class ResultadoPerfil:
    perfil_solicitado: str
    perfil_efectivo: str
    directorio: Path
    videos: tuple[Path, ...]
    duracion_objetivo: float
    motivo_fallback: str | None = None


def _entero(datos: Mapping[str, object], clave: str, predeterminado: int) -> int:
    try:
        return int(datos.get(clave, predeterminado))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"exportacion.{clave} debe ser entero") from exc


def _perfil_desde_json(
    datos: Mapping[str, object], predeterminado: PerfilVideo
) -> PerfilVideo:
    config = PerfilVideo(
        backend=str(datos.get("backend", predeterminado.backend)),
        fps=_entero(datos, "fps", predeterminado.fps),
        ancho_horizontal=_entero(datos, "ancho_horizontal", predeterminado.ancho_horizontal),
        alto_horizontal=_entero(datos, "alto_horizontal", predeterminado.alto_horizontal),
        ancho_vertical=_entero(datos, "ancho_vertical", predeterminado.ancho_vertical),
        alto_vertical=_entero(datos, "alto_vertical", predeterminado.alto_vertical),
        crf=_entero(datos, "crf", predeterminado.crf),
        preset=str(datos.get("preset", predeterminado.preset)),
        codec=str(datos.get("codec", predeterminado.codec)),
        pix_fmt=str(datos.get("pix_fmt", predeterminado.pix_fmt)),
        real_esrgan=bool(datos.get("real_esrgan", predeterminado.real_esrgan)),
    )
    if config.backend not in {"opencv", "ffmpeg"}:
        raise ValueError("El backend del perfil debe ser opencv o ffmpeg")
    if not 1 <= config.fps <= 120:
        raise ValueError("Los FPS del perfil deben estar entre 1 y 120")
    dimensiones = (
        config.ancho_horizontal, config.alto_horizontal,
        config.ancho_vertical, config.alto_vertical,
    )
    if any(valor < 64 or valor > 7680 or valor % 2 for valor in dimensiones):
        raise ValueError("Las dimensiones del perfil deben ser pares, entre 64 y 7680")
    if not 0 <= config.crf <= 35:
        raise ValueError("El CRF del perfil debe estar entre 0 y 35")
    if config.preset not in {
        "ultrafast", "superfast", "veryfast", "faster", "fast",
        "medium", "slow", "slower", "veryslow",
    }:
        raise ValueError("Preset FFmpeg desconocido en el perfil")
    if config.codec not in {"libx264", "libx265"}:
        raise ValueError("El codec del perfil debe ser libx264 o libx265")
    if config.pix_fmt not in {"yuv420p", "yuv420p10le"}:
        raise ValueError("El formato de pixel del perfil no esta permitido")
    return config


def cargar_configuracion(datos: Mapping[str, object] | None) -> ConfigPerfiles:
    datos = datos or {}
    perfiles_json = datos.get("perfiles", {})
    if not isinstance(perfiles_json, Mapping):
        raise ValueError("exportacion.perfiles debe ser un objeto JSON")
    base = {
        PERFIL_ESTANDAR: PerfilVideo("opencv", 30, 1920, 1080, 1080, 1920, 20, "medium"),
        PERFIL_ALTA: PerfilVideo("ffmpeg", 60, 3840, 2160, 2160, 3840, 16, "slow"),
        PERFIL_ULTRA: PerfilVideo(
            "ffmpeg", 60, 3840, 2160, 2160, 3840, 15, "slow", real_esrgan=True
        ),
    }
    perfiles: dict[str, PerfilVideo] = {}
    for nombre, predeterminado in base.items():
        valores = perfiles_json.get(nombre, {})
        if not isinstance(valores, Mapping):
            raise ValueError(f"exportacion.perfiles.{nombre} debe ser un objeto JSON")
        perfiles[nombre] = _perfil_desde_json(valores, predeterminado)
    perfil = str(datos.get("perfil", PERFIL_ULTRA)).lower()
    if perfil not in PERFILES:
        raise ValueError(f"Perfil desconocido: {perfil}")
    fallback = datos.get("fallback_ultra", PERFIL_ALTA)
    if fallback in {"", False, None}:
        fallback = None
    else:
        fallback = str(fallback).lower()
        if fallback not in {PERFIL_ESTANDAR, PERFIL_ALTA}:
            raise ValueError("exportacion.fallback_ultra debe ser estandar, alta_calidad o null")
    interpolacion = bool(datos.get("interpolacion_movimiento", False))
    if interpolacion:
        raise ValueError(
            "La interpolacion de movimiento no esta implementada; use duplicacion de fotogramas"
        )
    return ConfigPerfiles(perfil, fallback, interpolacion, perfiles)


def reservar_directorio(carpeta_sesion: Path, nombre: str) -> Path:
    """Crea una salida nueva sin sobrescribir ejecuciones ni archivos anteriores."""
    raiz = Path(carpeta_sesion).resolve() / "exportaciones"
    raiz.mkdir(parents=True, exist_ok=True)
    candidato = raiz / nombre
    indice = 2
    while candidato.exists():
        candidato = raiz / f"{nombre}_{indice:03d}"
        indice += 1
    candidato.mkdir()
    return candidato


def _recortar_y_escalar(imagen, ancho: int, alto: int):
    alto_src, ancho_src = imagen.shape[:2]
    aspecto_destino = ancho / alto
    aspecto_src = ancho_src / alto_src
    if aspecto_src > aspecto_destino:
        nuevo_ancho = max(1, round(alto_src * aspecto_destino))
        izquierda = (ancho_src - nuevo_ancho) // 2
        imagen = imagen[:, izquierda:izquierda + nuevo_ancho]
    elif aspecto_src < aspecto_destino:
        nuevo_alto = max(1, round(ancho_src / aspecto_destino))
        arriba = (alto_src - nuevo_alto) // 2
        imagen = imagen[arriba:arriba + nuevo_alto, :]
    interpolacion = cv2.INTER_AREA if imagen.shape[1] >= ancho else cv2.INTER_LANCZOS4
    return cv2.resize(imagen, (ancho, alto), interpolation=interpolacion)


def _exportar_opencv(
    archivos: Sequence[Path],
    destino: Path,
    fotos_por_segundo: float,
    perfil: PerfilVideo,
    progreso: Callable[[str], None] | None,
) -> tuple[Path, ...]:
    total = max(1, round(len(archivos) * perfil.fps / fotos_por_segundo))
    trabajos = (
        ("timelapse_horizontal.mp4", perfil.ancho_horizontal, perfil.alto_horizontal),
        ("timelapse_tiktok_9x16.mp4", perfil.ancho_vertical, perfil.alto_vertical),
    )
    escritores = []
    temporales = []
    salidas = []
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    try:
        for nombre, ancho, alto in trabajos:
            salida = destino / nombre
            temporal = destino / f".{Path(nombre).stem}.tmp.mp4"
            escritor = cv2.VideoWriter(str(temporal), fourcc, perfil.fps, (ancho, alto))
            if not escritor.isOpened():
                raise RuntimeError(f"OpenCV no pudo abrir el codificador para {nombre}")
            escritores.append((escritor, ancho, alto))
            temporales.append(temporal)
            salidas.append(salida)
        indice_anterior = -1
        imagen = None
        for indice_salida in range(total):
            indice_origen = min(
                len(archivos) - 1,
                int(indice_salida * fotos_por_segundo / perfil.fps),
            )
            if indice_origen != indice_anterior:
                imagen = cv2.imread(str(archivos[indice_origen]), cv2.IMREAD_COLOR)
                if imagen is None:
                    raise RuntimeError(f"No se pudo leer {archivos[indice_origen].name}")
                indice_anterior = indice_origen
            for escritor, ancho, alto in escritores:
                escritor.write(_recortar_y_escalar(imagen, ancho, alto))
            if progreso and (indice_salida == 0 or (indice_salida + 1) % 300 == 0):
                progreso(f"OpenCV: {indice_salida + 1}/{total} fotogramas duplicados")
    finally:
        for escritor, _, _ in escritores:
            escritor.release()
    for temporal, salida in zip(temporales, salidas):
        if not temporal.is_file() or temporal.stat().st_size == 0:
            raise RuntimeError(f"OpenCV no produjo un MP4 valido: {salida.name}")
        temporal.replace(salida)
    return tuple(salidas)


def _video_config(perfil: PerfilVideo) -> VideoConfig:
    return VideoConfig(
        crf=perfil.crf,
        preset=perfil.preset,
        codec=perfil.codec,
        pix_fmt=perfil.pix_fmt,
        ancho_horizontal=perfil.ancho_horizontal,
        alto_horizontal=perfil.alto_horizontal,
        ancho_vertical=perfil.ancho_vertical,
        alto_vertical=perfil.alto_vertical,
    )


def _guardar_informe(directorio: Path, datos: Mapping[str, object]) -> None:
    (directorio / "informe_exportacion.json").write_text(
        json.dumps(datos, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8"
    )


def _ejecutar_perfil(
    originales: Sequence[Path],
    carpeta_sesion: Path,
    nombre: str,
    perfil: PerfilVideo,
    config_mejora: MejoraConfig,
    fotos_por_segundo: float,
    base: Path,
    progreso: Callable[[str], None] | None,
) -> ResultadoPerfil:
    directorio = reservar_directorio(carpeta_sesion, nombre)
    if progreso:
        progreso(f"Perfil {nombre}: salida nueva en {directorio}")
    if perfil.real_esrgan:
        config_mejora = replace(
            config_mejora,
            real_esrgan=replace(config_mejora.real_esrgan, habilitado=True),
        )
    else:
        config_mejora = replace(
            config_mejora,
            real_esrgan=replace(config_mejora.real_esrgan, habilitado=False),
        )
    try:
        procesadas = procesar_secuencia(
            originales,
            directorio / "fotogramas_procesados",
            config_mejora,
            base=base,
            progreso=progreso,
        )
    except (RealESRGANError, RealESRGANNoDisponibleError) as exc:
        _guardar_informe(
            directorio,
            {
                "version": 1,
                "estado": "fallido",
                "perfil_solicitado": nombre,
                "motivo": str(exc),
                "fotografias_originales": len(originales),
                "originales_modificados": False,
            },
        )
        raise
    if perfil.backend == "opencv":
        videos = _exportar_opencv(
            procesadas, directorio, fotos_por_segundo, perfil, progreso
        )
    else:
        videos = tuple(
            exportar_videos(
                procesadas,
                directorio,
                fotos_por_segundo,
                perfil.fps,
                _video_config(perfil),
                progreso=progreso,
            )
        )
    duracion = len(originales) / fotos_por_segundo
    _guardar_informe(
        directorio,
        {
            "version": 1,
            "perfil_solicitado": nombre,
            "perfil_efectivo": nombre,
            "fotografias_originales": len(originales),
            "duracion_objetivo_seg": duracion,
            "duplicacion_fotogramas": True,
            "interpolacion_movimiento": False,
            "perfil": asdict(perfil),
            "videos": [video.name for video in videos],
        },
    )
    return ResultadoPerfil(nombre, nombre, directorio, videos, duracion)


def exportar_perfil(
    originales: Sequence[Path],
    carpeta_sesion: Path,
    config_general: Mapping[str, object],
    *,
    perfil_solicitado: str | None = None,
    base: Path | None = None,
    progreso: Callable[[str], None] | None = None,
) -> ResultadoPerfil:
    """Procesa siempre los originales y exporta sin reemplazar resultados existentes."""
    originales = [Path(p).resolve() for p in originales]
    if not originales or any(not p.is_file() for p in originales):
        raise ValueError("El perfil necesita fotografias originales existentes")
    try:
        fotos_por_segundo = float(config_general.get("fotos_por_segundo", 6.0))
    except (TypeError, ValueError) as exc:
        raise ValueError("fotos_por_segundo debe ser numerico") from exc
    if not math.isfinite(fotos_por_segundo) or not 0.1 <= fotos_por_segundo <= 60:
        raise ValueError("fotos_por_segundo debe estar entre 0.1 y 60")
    config_perfiles = cargar_configuracion(config_general.get("exportacion"))
    solicitado = (perfil_solicitado or config_perfiles.perfil).lower()
    if solicitado not in PERFILES:
        raise ValueError(f"Perfil desconocido: {solicitado}")
    config_mejora = cargar_mejora(config_general.get("mejora"))
    base = (base or Path(__file__).resolve().parent).resolve()

    try:
        return _ejecutar_perfil(
            originales,
            Path(carpeta_sesion),
            solicitado,
            config_perfiles.perfiles[solicitado],
            config_mejora,
            fotos_por_segundo,
            base,
            progreso,
        )
    except (RealESRGANError, RealESRGANNoDisponibleError) as exc:
        if solicitado != PERFIL_ULTRA or config_perfiles.fallback_ultra is None:
            raise
        motivo = str(exc)
        if progreso:
            progreso(
                f"AVISO: Ultra IA no disponible ({motivo}). "
                f"Se usara {config_perfiles.fallback_ultra} sin tocar originales."
            )
        fallback = config_perfiles.fallback_ultra
        resultado = _ejecutar_perfil(
            originales,
            Path(carpeta_sesion),
            fallback,
            config_perfiles.perfiles[fallback],
            config_mejora,
            fotos_por_segundo,
            base,
            progreso,
        )
        _guardar_informe(
            resultado.directorio,
            {
                "version": 1,
                "perfil_solicitado": solicitado,
                "perfil_efectivo": fallback,
                "motivo_fallback": motivo,
                "fotografias_originales": len(originales),
                "duracion_objetivo_seg": resultado.duracion_objetivo,
                "duplicacion_fotogramas": True,
                "interpolacion_movimiento": False,
                "perfil": asdict(config_perfiles.perfiles[fallback]),
                "videos": [video.name for video in resultado.videos],
            },
        )
        return replace(
            resultado,
            perfil_solicitado=solicitado,
            motivo_fallback=motivo,
        )
