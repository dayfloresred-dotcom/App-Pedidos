"""Verificación: archivo manual 'Informe de Ventas y Stock' (foto) vs fuentes vivas.

Compara por SKU:
  1. Ventas por sucursal (archivo) vs consulta viva a Plex (ventana VENTAS_VENTANA_DIAS)
  2. Stock por sucursal (archivo) vs Plex vivo
  3. Cajas Stock CD (archivo) vs stock de Quantio ya matcheado contra el catálogo Plex

Uso (dentro del contenedor): python scripts/verificar_informe.py <ruta_informe.csv>
"""
import csv
import os
import sys
from collections import Counter

sys.path.insert(0, os.environ.get('APP_DIR', '/app'))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import SUCURSALES
import fuentes_plex
import fuentes_quantio
from database import get_mapeo_cd

EXCLUIR = {'17', '33'}


def _extract_num(s):
    return s.replace('Suc. ', '').replace('SUC', '').strip()


def parsear_informe(ruta):
    """Mismo criterio de parseo que data_loader.load_productos()."""
    headers, header_row = [], -1
    suc_vend, suc_stock = {}, {}
    cd_idx = None
    no_mapeadas = set()
    filas = {}
    with open(ruta, encoding='latin-1') as f:
        reader = csv.reader(f, delimiter=';')
        for i, row in enumerate(reader):
            if not headers and row and row[0].strip() == 'IDProducto':
                headers, header_row = row, i
                for idx, h in enumerate(headers):
                    hs = h.strip()
                    if hs == 'Cajas Stock CD':
                        cd_idx = idx
                    elif h.startswith('Cajas Vend. Total') or h.startswith('Cajas Stock Total'):
                        continue
                    elif h.startswith('Cajas Vend'):
                        num = _extract_num(h.replace('Cajas Vend. ', '').replace('Cajas Vend ', ''))
                        if num in EXCLUIR:
                            continue
                        if num in SUCURSALES:
                            suc_vend[SUCURSALES[num]] = idx
                        else:
                            no_mapeadas.add(num)
                    elif h.startswith('Cajas Stock'):
                        num = _extract_num(h.replace('Cajas Stock ', ''))
                        if num in EXCLUIR:
                            continue
                        if num in SUCURSALES:
                            suc_stock[SUCURSALES[num]] = idx
                        else:
                            no_mapeadas.add(num)
            elif header_row >= 0 and i > header_row and row and len(row) > 5 and row[3].strip():
                sku = row[0].strip()

                def _num(idx):
                    try:
                        return int(float(row[idx].replace(',', '.'))) if row[idx].strip() else 0
                    except (ValueError, IndexError):
                        return 0

                filas[sku] = {
                    'descripcion': row[4],
                    'rubro': row[3].strip(),
                    'ventas': {s: _num(ix) for s, ix in suc_vend.items()},
                    'stock': {s: _num(ix) for s, ix in suc_stock.items()},
                    'stock_cd': max(0, _num(cd_idx)) if cd_idx is not None else 0,
                }
    return filas, sorted(suc_vend), sorted(no_mapeadas)


def comparar_celdas(nombre, archivo, vivo, sucursales, skus):
    """Compara métricas por (sku, sucursal). Solo celdas donde algún lado != 0."""
    exact = dentro2 = total = 0
    suma_abs = 0
    peores = []
    for sku in skus:
        fa = archivo[sku][nombre]
        fv = vivo.get(sku, {})
        for s in sucursales:
            a, v = fa.get(s, 0), int(fv.get(s, 0))
            if a == 0 and v == 0:
                continue
            total += 1
            d = abs(a - v)
            suma_abs += d
            if d == 0:
                exact += 1
            elif d <= 2:
                dentro2 += 1
            else:
                peores.append((d, sku, s, a, v))
    peores.sort(reverse=True)
    print(f'\n== {nombre.upper()} por sucursal (celdas con movimiento: {total}) ==')
    if not total:
        print('  sin celdas para comparar')
        return
    print(f'  exactas: {exact} ({100 * exact / total:.1f}%) | dif <=2: {dentro2} '
          f'({100 * (exact + dentro2) / total:.1f}% acumulado) | dif >2: {len(peores)}')
    print(f'  diferencia absoluta promedio: {suma_abs / total:.2f}')
    if peores:
        print('  10 peores (dif | sku | sucursal | archivo -> vivo):')
        for d, sku, s, a, v in peores[:10]:
            print(f'    {d:>5} | {sku} | {s} | {a} -> {v}')


def main():
    ruta = sys.argv[1]
    archivo, sucs_archivo, no_mapeadas = parsear_informe(ruta)
    print(f'ARCHIVO: {len(archivo)} productos | sucursales mapeadas: {len(sucs_archivo)}')
    if no_mapeadas:
        print(f'  sucursales del archivo SIN mapear (ignoradas): {sorted(no_mapeadas)}')
    cd_archivo = {sku: f['stock_cd'] for sku, f in archivo.items() if f['stock_cd'] > 0}
    print(f'  con Cajas Stock CD > 0: {len(cd_archivo)}')

    print('\nConsultando Plex vivo...')
    plex = fuentes_plex.cargar()
    print(f'PLEX: {len(plex["productos"])} productos | {len(plex["ventas"])} con ventas | '
          f'{len(plex["stock"])} con stock')

    en_plex = [sku for sku in archivo if sku in plex['productos']]
    faltan = [sku for sku in archivo if sku not in plex['productos']]
    print(f'\n== COBERTURA == {len(en_plex)}/{len(archivo)} SKUs del archivo existen en Plex '
          f'({100 * len(en_plex) / len(archivo):.1f}%)')
    if faltan:
        print(f'  faltan en Plex ({len(faltan)}), muestra: {faltan[:10]}')

    comparar_celdas('ventas', archivo, plex['ventas'], sucs_archivo, en_plex)
    comparar_celdas('stock', archivo, plex['stock'], sucs_archivo, en_plex)

    print('\nConsultando Quantio (CD) vivo...')
    if not fuentes_quantio.configurada():
        print('QUANTIO: fuente deshabilitada — no se puede verificar stock CD')
        return
    filas_cd = fuentes_quantio.cargar_stock_cd()
    stock_cd, no_match = fuentes_quantio.matchear_cd(filas_cd, plex['productos'], get_mapeo_cd())
    print(f'QUANTIO: {len(filas_cd)} filas con stock > 0 | matcheadas a {len(stock_cd)} SKUs | '
          f'sin match: {len(no_match)}')

    ambos = set(cd_archivo) & set(stock_cd)
    solo_archivo = set(cd_archivo) - set(stock_cd)
    solo_quantio = set(stock_cd) - set(cd_archivo)
    print(f'\n== STOCK CD ==')
    print(f'  archivo>0: {len(cd_archivo)} | quantio>0: {len(stock_cd)} | en ambos: {len(ambos)}')
    print(f'  cobertura del archivo por quantio: {100 * len(ambos) / max(1, len(cd_archivo)):.1f}%')
    print(f'  total unidades: archivo {sum(cd_archivo.values())} | quantio {sum(stock_cd.values())}')

    exact = sum(1 for sku in ambos if cd_archivo[sku] == stock_cd[sku])
    dentro2 = sum(1 for sku in ambos if 0 < abs(cd_archivo[sku] - stock_cd[sku]) <= 2)
    print(f'  cantidades en comunes: exactas {exact} ({100 * exact / max(1, len(ambos)):.1f}%) | '
          f'dif <=2: {dentro2} | dif >2: {len(ambos) - exact - dentro2}')

    if solo_archivo:
        print(f'\n  SOSPECHOSOS — con stock CD en archivo pero 0/ausente en quantio: {len(solo_archivo)}')
        detalle = sorted(solo_archivo, key=lambda k: -cd_archivo[k])[:15]
        for sku in detalle:
            d = archivo[sku]['descripcion'][:45]
            en_p = 'en Plex' if sku in plex['productos'] else 'NO en Plex'
            print(f'    {sku} | cd_archivo={cd_archivo[sku]} | {en_p} | {d}')
    print(f'  solo en quantio (stock nuevo desde la foto): {len(solo_quantio)}')

    dist = Counter(abs(cd_archivo[sku] - stock_cd[sku]) for sku in ambos)
    print(f'  distribución |dif| en comunes: ' +
          ', '.join(f'{d}:{n}' for d, n in sorted(dist.items())[:8]))


if __name__ == '__main__':
    main()
