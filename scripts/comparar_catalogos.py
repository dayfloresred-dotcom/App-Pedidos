"""Aceptación: compara el catálogo por FUENTES vs el catálogo por ARCHIVOS.
Uso: docker compose -f docker-compose.prod.yml exec pedidos python scripts/comparar_catalogos.py"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import data_loader
import fuentes
import fuentes_comparador
import fuentes_plex
import fuentes_quantio
from database import get_mapeo_cd

archivos = data_loader.load_productos()
por_sku_arch = {p['sku']: p for p in archivos}
print(f'Catálogo por ARCHIVOS: {len(archivos)} productos')

plex = fuentes_plex.cargar()
precios = fuentes_comparador.cargar()
stock_cd = {}
if fuentes_quantio.configurada():
    stock_cd, no_match = fuentes_quantio.matchear_cd(
        fuentes_quantio.cargar_stock_cd(), plex['productos'], get_mapeo_cd())
    print(f'Stock CD: {len(stock_cd)} matcheados, {len(no_match)} sin match')
else:
    print('Stock CD: fuente Quantio deshabilitada (sin conectividad/Fase 0)')
cat = fuentes.construir_catalogo(plex, precios, stock_cd)
por_sku_fue = {p['sku']: p for p in cat}
print(f'Catálogo por FUENTES : {len(cat)} productos')
print(f"Precios comparador: {len(precios['precios'])} skus | stale: {precios['stale']}")

comunes = sorted(set(por_sku_arch) & set(por_sku_fue))
solo_arch = len(por_sku_arch) - len(comunes)
solo_fue = len(por_sku_fue) - len(comunes)
print(f'En común: {len(comunes)} | solo archivos: {solo_arch} | solo fuentes: {solo_fue}')

con_precio_arch = sum(1 for p in archivos if p['drogueria'])
con_precio_fue = sum(1 for p in cat if p['drogueria'])
print(f'Con droguería asignada: archivos {con_precio_arch} | fuentes {con_precio_fue}')

muestra = random.sample(comunes, min(15, len(comunes)))
print('\nsku | drog archivos->fuentes | precio a->f | stockCD a->f | ventas CERRO a->f')
for sku in muestra:
    a, f = por_sku_arch[sku], por_sku_fue[sku]
    print(f"{sku} | {a['drogueria'] or '-'}->{f['drogueria'] or '-'} | "
          f"{a['mejor_precio']}->{f['mejor_precio']} | {a['stock_cd']}->{f['stock_cd']} | "
          f"{a['ventas'].get('CERRO', 0)}->{f['ventas'].get('CERRO', 0)}")

solo_archivos_skus = sorted(set(por_sku_arch) - set(por_sku_fue))
if solo_archivos_skus:
    print(f"\nDIAGNOSTICO solo-archivos ({len(solo_archivos_skus)}): que dice Plex vivo de una muestra?")
    muestra_sa = random.sample(solo_archivos_skus, min(8, len(solo_archivos_skus)))
    conn = fuentes_plex._conn()
    try:
        with conn.cursor() as cur:
            marcadores = ','.join(['%s'] * len(muestra_sa))
            cur.execute(f"""SELECT m.CodPlex AS sku, r.Rubro AS rubro
                FROM medicamentos m LEFT JOIN rubros r ON r.CodRubro = m.CodRubro
                WHERE m.CodPlex IN ({marcadores})""", muestra_sa)
            vivos = {str(x['sku']): x['rubro'] for x in cur.fetchall()}
    finally:
        conn.close()
    for sku in muestra_sa:
        arch = por_sku_arch[sku]
        print(f"  {sku} | rubro archivo: {arch['rubro']!r} | rubro Plex vivo: {vivos.get(sku, 'NO EXISTE')!r}")
