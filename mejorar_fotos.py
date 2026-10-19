"""CLI para mejorar y exportar fotografias de una sesion existente."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from exportador_video import cargar_configuracion as cargar_video
from exportador_video import exportar_videos
from mejora_imagenes import cargar_configuracion as cargar_mejora
from mejora_imagenes import listar_originales, procesar_secuencia


BASE = Path(__file__).resolve().parent
RESULTADOS = BASE / "resultados"


def ultimo_resultado() -> Path:
    if not RESULTADOS.exists():
        raise RuntimeError(f"No existe la carpeta de resultados: {RESULTADOS}")
    carpetas = sorted(
        (p for p in RESULTADOS.iterdir() if p.is_dir() and listar_originales(p)),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not carpetas:
        raise RuntimeError("No hay carpetas con fotografias capa_*.jpg en resultados")
    return carpetas[0]


def cargar_json(ruta: Path) -> dict:
    if not ruta.is_file():
        raise FileNotFoundError(
            f"No existe {ruta.name}. Copia config.example.json como config.json y completa tus datos."
        )
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    if not isinstance(datos, dict):
        raise ValueError("La raiz de la configuracion debe ser un objeto JSON")
    return datos


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Mejora JPG originales sin sobrescribirlos y genera MP4 de alta calidad"
    )
    parser.add_argument(
        "--carpeta", type=Path, help="Sesion de resultados; por defecto se usa la mas reciente"
    )
    parser.add_argument("--config", type=Path, default=BASE / "config.json")
    parser.add_argument("--sin-video", action="store_true", help="Solo crea imagenes mejoradas")
    parser.add_argument("--fotos-por-segundo", type=float, help="Reemplaza el valor de config.json")
    parser.add_argument("--fps-salida", type=int, help="Reemplaza el valor de config.json")
    args = parser.parse_args()

    config_general = cargar_json(args.config.resolve())
    carpeta = (args.carpeta or ultimo_resultado()).resolve()
    originales = listar_originales(carpeta)
    if not originales:
        raise RuntimeError(f"No hay fotografias capa_*.jpg en {carpeta}")

    print(f"Sesion: {carpeta}", flush=True)
    print(f"Originales preservados: {len(originales)}", flush=True)
    config_mejora = cargar_mejora(config_general.get("mejora"))
    mejoradas = procesar_secuencia(
        originales,
        carpeta / "imagenes_mejoradas",
        config_mejora,
        base=BASE,
        progreso=lambda mensaje: print(mensaje, flush=True),
    )
    print(f"Fotografias mejoradas: {len(mejoradas)}", flush=True)

    if not args.sin_video:
        fotos_por_segundo = (
            args.fotos_por_segundo
            if args.fotos_por_segundo is not None
            else float(config_general.get("fotos_por_segundo", 6.0))
        )
        fps_configurado = (
            args.fps_salida
            if args.fps_salida is not None
            else config_general.get("fps_timelapse", 30)
        )
        try:
            fps_salida = int(fps_configurado)
        except (TypeError, ValueError):
            fps_salida = 30
        if not 1 <= fps_salida <= 120:
            fps_salida = 30
        salidas = exportar_videos(
            mejoradas,
            carpeta,
            fotos_por_segundo,
            fps_salida,
            cargar_video(config_general.get("video")),
            progreso=lambda mensaje: print(mensaje, flush=True),
        )
        for salida in salidas:
            print(f"Creado: {salida}", flush=True)
    print("LISTO: los JPG originales permanecen intactos.", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
