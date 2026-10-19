"""Recrea MP4 desde las fotos JPG existentes; no necesita conectarse a la impresora ni a Tapo."""
import argparse
import json
from pathlib import Path

from perfiles_exportacion import PERFILES, exportar_perfil

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


def generar(carpeta, entrada, salida, perfil=None):
    carpeta = Path(carpeta).resolve()
    # Cada perfil parte siempre de los originales; no encadena reescalados previos.
    fotos = sorted(carpeta.glob('capa_*.jpg'))
    if not fotos:
        raise RuntimeError(f'No se encontraron fotos en {carpeta}')
    print(f'Carpeta: {carpeta}')
    config_path = BASE / 'config.json'
    config = json.loads(config_path.read_text(encoding='utf-8')) if config_path.is_file() else {}
    config['fotos_por_segundo'] = entrada
    if salida is not None:
        nombre = perfil or str(config.get('exportacion', {}).get('perfil', 'ultra_ia'))
        exportacion = config.setdefault('exportacion', {})
        perfiles = exportacion.setdefault('perfiles', {})
        perfiles.setdefault(nombre, {})['fps'] = salida
    print(f'Fotografias originales: {len(fotos)} | velocidad: {entrada:g} fotos/s', flush=True)
    resultado = exportar_perfil(
        fotos, carpeta, config, perfil_solicitado=perfil, base=BASE,
        progreso=lambda mensaje: print(mensaje, flush=True),
    )
    print(f'Perfil solicitado: {resultado.perfil_solicitado} | efectivo: {resultado.perfil_efectivo}')
    for salida_archivo in resultado.videos:
        print('OK:', salida_archivo, flush=True)
    print('LISTO: la impresion no necesita repetirse.', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Recuperar timelapse desde fotografias')
    parser.add_argument('--carpeta', type=Path, help='Carpeta de resultados concreta; por defecto la mas reciente')
    parser.add_argument('--fotos-por-segundo', type=float, default=6.0, help='6 = 65 fotografias duran 10.8 segundos')
    parser.add_argument('--fps-salida', type=int, help='Reemplaza los FPS definidos por el perfil')
    parser.add_argument('--perfil', choices=PERFILES, help='Perfil; por defecto usa config.json')
    args = parser.parse_args()
    if not 0.1 <= args.fotos_por_segundo <= 60:
        parser.error('--fotos-por-segundo debe estar entre 0.1 y 60')
    if args.fps_salida is not None and not 1 <= args.fps_salida <= 120:
        parser.error('--fps-salida debe estar entre 1 y 120')
    try:
        generar(
            args.carpeta if args.carpeta else ultimo_resultado(),
            args.fotos_por_segundo,
            args.fps_salida,
            args.perfil,
        )
    except Exception as exc:
        raise SystemExit(f'ERROR: {exc}')
