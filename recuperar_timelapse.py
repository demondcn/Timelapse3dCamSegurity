"""Recrea MP4 desde las fotos JPG existentes; no necesita conectarse a la impresora ni a Tapo."""
import argparse
from pathlib import Path

from exportador_video import cargar_configuracion, exportar_videos

BASE = Path(__file__).resolve().parent
RESULTADOS = BASE / 'resultados'


def ultimo_resultado():
    if not RESULTADOS.exists():
        raise RuntimeError(f'No existe la carpeta de resultados: {RESULTADOS}')
    carpetas = sorted(
        (p for p in RESULTADOS.iterdir() if p.is_dir() and list(p.glob('capa_*.jpg'))),
        key=lambda p: p.stat().st_mtime, reverse=True
    )
    if not carpetas:
        raise RuntimeError('No hay carpetas con fotografias capa_*.jpg en resultados.')
    return carpetas[0]


def generar(carpeta, entrada, salida):
    mejoradas = carpeta / 'imagenes_mejoradas'
    fotos = sorted(mejoradas.glob('capa_*.jpg')) if mejoradas.is_dir() else []
    if fotos:
        print('Usando fotografias mejoradas existentes.', flush=True)
    else:
        fotos = sorted(carpeta.glob('capa_*.jpg'))
    if not fotos:
        raise RuntimeError(f'No se encontraron fotos en {carpeta}')
    print(f'Carpeta: {carpeta}')
    print(f'Fotografias: {len(fotos)} | velocidad: {entrada:g} fotos/s | MP4: {salida} fps', flush=True)
    creados = exportar_videos(
        fotos, carpeta, entrada, salida, cargar_configuracion({}),
        progreso=lambda mensaje: print(mensaje, flush=True),
    )
    for salida_archivo in creados:
        print('OK:', salida_archivo, flush=True)
    print('LISTO: la impresion no necesita repetirse.', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Recuperar timelapse desde fotografias')
    parser.add_argument('--carpeta', type=Path, help='Carpeta de resultados concreta; por defecto la mas reciente')
    parser.add_argument('--fotos-por-segundo', type=float, default=6.0, help='6 = 65 fotografias duran 10.8 segundos')
    parser.add_argument('--fps-salida', type=int, default=30, help='FPS del MP4 generado')
    args = parser.parse_args()
    if not 0.1 <= args.fotos_por_segundo <= 60:
        parser.error('--fotos-por-segundo debe estar entre 0.1 y 60')
    if not 1 <= args.fps_salida <= 120:
        parser.error('--fps-salida debe estar entre 1 y 120')
    try:
        generar(args.carpeta if args.carpeta else ultimo_resultado(), args.fotos_por_segundo, args.fps_salida)
    except Exception as exc:
        raise SystemExit(f'ERROR: {exc}')
