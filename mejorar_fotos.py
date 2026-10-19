"""CLI para mejorar y exportar fotografias de una sesion existente."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from mejora_imagenes import cargar_configuracion as cargar_mejora
from mejora_imagenes import listar_originales, procesar_secuencia
from perfiles_exportacion import PERFILES, exportar_perfil, reservar_directorio


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
    parser.add_argument(
        "--perfil", choices=PERFILES,
        help="estandar, alta_calidad o ultra_ia; por defecto usa config.json",
    )
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
    if args.fotos_por_segundo is not None:
        config_general["fotos_por_segundo"] = args.fotos_por_segundo
    if args.fps_salida is not None:
        perfil_objetivo = args.perfil or str(
            config_general.get("exportacion", {}).get("perfil", "ultra_ia")
        )
        exportacion = config_general.setdefault("exportacion", {})
        perfiles = exportacion.setdefault("perfiles", {})
        perfiles.setdefault(perfil_objetivo, {})["fps"] = args.fps_salida

    if args.sin_video:
        destino = reservar_directorio(carpeta, "solo_mejora") / "fotogramas_procesados"
        mejoradas = procesar_secuencia(
            originales,
            destino,
            cargar_mejora(config_general.get("mejora")),
            base=BASE,
            progreso=lambda mensaje: print(mensaje, flush=True),
        )
        print(f"Fotografias mejoradas: {len(mejoradas)} en {destino}", flush=True)
    else:
        resultado = exportar_perfil(
            originales,
            carpeta,
            config_general,
            perfil_solicitado=args.perfil,
            base=BASE,
            progreso=lambda mensaje: print(mensaje, flush=True),
        )
        print(
            f"Perfil solicitado: {resultado.perfil_solicitado} | "
            f"efectivo: {resultado.perfil_efectivo}",
            flush=True,
        )
        print(f"Duracion objetivo: {resultado.duracion_objetivo:.3f} s", flush=True)
        for salida in resultado.videos:
            print(f"Creado: {salida}", flush=True)
    print("LISTO: los JPG originales permanecen intactos.", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
