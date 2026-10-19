"""Recrea MP4 desde las fotos JPG existentes; no necesita conectarse a la impresora ni a Tapo."""
import argparse
import os
import shutil
import subprocess
from pathlib import Path

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


def ejecutar(cmd):
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr[-2500:])


def generar(carpeta, entrada, salida):
    fotos = sorted(carpeta.glob('capa_*.jpg'))
    if not fotos:
        raise RuntimeError(f'No se encontraron fotos en {carpeta}')
    if not shutil.which('ffmpeg'):
        raise RuntimeError('FFmpeg no esta instalado o no esta en PATH. Ejecuta: winget install --id Gyan.FFmpeg -e')
    print(f'Carpeta: {carpeta}')
    print(f'Fotografias: {len(fotos)} | velocidad: {entrada:g} fotos/s | MP4: {salida} fps', flush=True)
    # Usamos concat con entradas explicitas, por si faltan JPG en la secuencia.
    # Duplicamos fotogramas al convertir a 30 FPS sin cambiar la duracion.
    concat = carpeta / '_fotogramas_exportacion.ffconcat'
    duracion = 1.0 / entrada
    def esc(p):
        # Formato de archivo concat para FFmpeg; las comillas simples se escapan.
        return str(p.resolve()).replace('\\', '/').replace("'", "'\\''")
    text = ['ffconcat version 1.0']
    for p in fotos:
        text.extend([f"file '{esc(p)}'", f'duration {duracion:.12f}'])
    text.append(f"file '{esc(fotos[-1])}'")
    concat.write_text('\n'.join(text)+'\n', encoding='utf-8')
    try:
        for nombre, vf in (
            ('timelapse_horizontal.mp4', 'scale=1920:1080:flags=lanczos,setsar=1'),
            ('timelapse_tiktok_9x16.mp4', 'crop=ih*9/16:ih,scale=1080:1920:flags=lanczos,setsar=1')
        ):
            salida_archivo = carpeta / nombre
            print('Generando:', nombre, flush=True)
            cmd = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
                   '-safe', '0', '-f', 'concat', '-i', str(concat),
                   '-vf', vf, '-r', str(salida), '-c:v', 'libx264', '-crf', '19',
                   '-preset', 'medium', '-pix_fmt', 'yuv420p', '-movflags', '+faststart',
                   str(salida_archivo)]
            ejecutar(cmd)
            print('OK:', salida_archivo, flush=True)
    finally:
        concat.unlink(missing_ok=True)
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
