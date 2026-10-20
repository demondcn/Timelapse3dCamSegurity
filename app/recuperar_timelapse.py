"""Reconstruye los dos MP4 directamente desde los JPG originales."""

import argparse
import json
from pathlib import Path

from .exportador_video import cargar_configuracion, exportar_videos


ROOT = Path(__file__).resolve().parent.parent
RESULTADOS = ROOT / "resultados"


def ultimo_resultado() -> Path:
    if not RESULTADOS.exists():
        raise RuntimeError(f"No existe la carpeta de resultados: {RESULTADOS}")
    carpetas = sorted(
        (p for p in RESULTADOS.iterdir() if p.is_dir() and any(p.glob("capa_*.jpg"))),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not carpetas:
        raise RuntimeError("No hay sesiones con fotografias capa_*.jpg")
    return carpetas[0]


def recuperar(carpeta: Path, fotos_por_segundo: float | None, fps_salida: int | None) -> None:
    carpeta = carpeta.resolve()
    fotos = sorted(carpeta.glob("capa_*.jpg"))
    if not fotos:
        raise RuntimeError(f"No se encontraron fotos en {carpeta}")

    config_path = ROOT / "config" / "config.json"
    config = json.loads(config_path.read_text(encoding="utf-8")) if config_path.is_file() else {}
    velocidad = float(
        fotos_por_segundo if fotos_por_segundo is not None
        else config.get("fotos_por_segundo", 6.0)
    )
    fps = int(fps_salida if fps_salida is not None else config.get("fps_timelapse", 30))
    video = cargar_configuracion(config.get("video"))

    print(f"Sesion: {carpeta}", flush=True)
    print(f"Fotografias originales: {len(fotos)}", flush=True)
    salidas = exportar_videos(
        fotos,
        carpeta,
        velocidad,
        fps,
        video,
        progreso=lambda mensaje: print(mensaje, flush=True),
    )
    for salida in salidas:
        print(f"OK: {salida}", flush=True)
    print("LISTO: los JPG originales permanecen intactos.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Recuperar MP4 desde fotografias existentes")
    parser.add_argument(
        "--carpeta", type=Path,
        help="Carpeta de sesion; por defecto se usa la mas reciente",
    )
    parser.add_argument("--fotos-por-segundo", type=float)
    parser.add_argument("--fps-salida", type=int)
    args = parser.parse_args()
    try:
        recuperar(
            args.carpeta if args.carpeta else ultimo_resultado(),
            args.fotos_por_segundo,
            args.fps_salida,
        )
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
