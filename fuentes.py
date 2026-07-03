"""Orquestador de fuentes automáticas: refresco resiliente con memoria
last-good por fuente + ensamblado del catálogo (misma estructura que
data_loader.load_productos)."""
import json
import os
import pickle

import fuentes_comparador
import fuentes_plex
import fuentes_quantio
from config import DATA_DIR
from database import get_mapeo_cd, set_fuente_estado
from data_loader import decidir_drogueria

_DIR_MEMORIA = DATA_DIR  # override en tests
NO_MATCH_JSON = 'cd_no_matcheados.json'


def _ruta_memoria(fuente):
    return os.path.join(_DIR_MEMORIA, f'fuente_{fuente}.pkl')


def _cargar_con_memoria(nombre, fn_cargar):
    """Intenta la fuente; si falla usa el último resultado bueno guardado.
    Devuelve (datos|None, info_estado)."""
    try:
        datos = fn_cargar()
        with open(_ruta_memoria(nombre), 'wb') as f:
            pickle.dump(datos, f)
        return datos, {'ok': True, 'error': None, 'desde_memoria': False}
    except Exception as e:
        error = f'{type(e).__name__}: {e}'
        ruta = _ruta_memoria(nombre)
        if os.path.exists(ruta):
            with open(ruta, 'rb') as f:
                return pickle.load(f), {'ok': False, 'error': error, 'desde_memoria': True}
        return None, {'ok': False, 'error': error, 'desde_memoria': False}


def construir_catalogo(plex, precios, stock_cd):
    """Pura: datos de conectores -> lista de productos con la MISMA
    estructura que produce data_loader.load_productos().

    Relevancia: el catálogo vivo de Plex trae TODOS los productos del rubro
    (cientos de miles, la mayoría históricos). Se incluye un producto solo si
    tiene alguna señal operativa: ventas en la ventana, stock en alguna
    sucursal, stock en el CD, o precio en el comparador — que es el universo
    que el reporte de presupuesto (pipeline de archivos) representaba."""
    catalogo = []
    mapa_precios = precios.get('precios', {})
    precios_ean = precios.get('precios_ean', {})
    alfabeta = precios.get('alfabeta', {})
    alfabeta_ean = precios.get('alfabeta_ean', {})
    for sku, p in plex['productos'].items():
        ean = p.get('ean', '')
        # precio: primero match por sku (sku_erp del comparador); fallback EAN
        pr = mapa_precios.get(sku) or (precios_ean.get(ean) if ean else None) or {}
        cant_cd = int(stock_cd.get(sku, 0))
        ventas = plex['ventas'].get(sku, {})
        stock = plex['stock'].get(sku, {})
        tiene_precio = bool(pr.get('SUD') or pr.get('SUIZO'))
        if not (ventas or stock or cant_cd > 0 or tiene_precio):
            continue  # sin señal operativa: fuera del catálogo
        drogueria, mejor_precio, drog_ext, _ = decidir_drogueria(
            cant_cd, pr.get('SUD'), pr.get('SUIZO'))
        sucs = set(ventas) | set(stock)
        necesidad, stock_real, ventas_out = {}, {}, {}
        for s in sucs:
            v = int(ventas.get(s, 0))
            st = int(stock.get(s, 0))
            necesidad[s] = max(0, v - st)
            stock_real[s] = st
            ventas_out[s] = v
        catalogo.append({
            'sku':          sku,
            'ean':          p['ean'],
            'descripcion':  p['descripcion'],
            'laboratorio':  p['laboratorio'],
            'rubro':        p['rubro'],
            'stock_cd':     cant_cd,
            'drogueria':    drogueria,
            'mejor_precio': mejor_precio,
            'drog_ext':     drog_ext,
            'troquel':      alfabeta.get(sku) or (alfabeta_ean.get(ean) if ean else None) or '0000000',
            'troquel_pres': p['troquel'],
            'necesidad':    necesidad,
            'stock_real':   stock_real,
            'ventas':       ventas_out,
        })
    return catalogo


def refrescar_fuentes():
    """Orquesta el refresco. Plex y comparador son críticas (con memoria);
    Quantio es opcional (si está deshabilitada, stock CD = archivo manual
    vía el pipeline de data_loader... o vacío si tampoco hay archivo)."""
    import data_loader

    resumen = {'ok': False, 'productos': 0, 'fuentes': {}, 'no_matcheados': 0}

    plex, info = _cargar_con_memoria('plex', fuentes_plex.cargar) \
        if fuentes_plex.configurada() else (None, {'ok': False, 'error': 'sin configurar', 'desde_memoria': False})
    info['filas'] = len(plex['productos']) if plex else 0
    resumen['fuentes']['plex'] = info
    set_fuente_estado('plex', info['ok'], info['filas'], info['error'])

    precios, info_p = _cargar_con_memoria('comparador', fuentes_comparador.cargar) \
        if fuentes_comparador.configurada() else (None, {'ok': False, 'error': 'sin configurar', 'desde_memoria': False})
    info_p['filas'] = len(precios['precios']) if precios else 0
    resumen['fuentes']['comparador'] = info_p
    set_fuente_estado('comparador', info_p['ok'], info_p['filas'], info_p['error'])

    stock_cd, no_match = {}, []
    if fuentes_quantio.configurada() and plex:
        filas, info_q = _cargar_con_memoria('quantio', fuentes_quantio.cargar_stock_cd)
        if filas is not None:
            stock_cd, no_match = fuentes_quantio.matchear_cd(
                filas, plex['productos'], get_mapeo_cd())
        info_q['filas'] = len(stock_cd)
        resumen['fuentes']['quantio'] = info_q
        set_fuente_estado('quantio', info_q['ok'], info_q['filas'], info_q['error'])
    else:
        # Fallback mientras no hay conectividad al Quantio del CD: conservar
        # el último stock CD conocido (viene del archivo manual o de la
        # corrida previa). Se actualiza cuando el admin sube el presupuesto.
        try:
            import data_loader as _dl
            stock_cd = {p['sku']: int(p.get('stock_cd') or 0)
                        for p in _dl.load_productos()
                        if int(p.get('stock_cd') or 0) > 0}
        except Exception:
            stock_cd = {}
        resumen['fuentes']['quantio'] = {'ok': False,
                                         'error': f'sin configurar (fallback: {len(stock_cd)} productos con stock CD del último catálogo)',
                                         'desde_memoria': False, 'filas': len(stock_cd)}

    if plex is None or precios is None:
        return resumen

    catalogo = construir_catalogo(plex, precios, stock_cd)
    resumen['productos'] = len(catalogo)
    resumen['no_matcheados'] = len(no_match)
    try:
        with open(os.path.join(_DIR_MEMORIA, NO_MATCH_JSON), 'w', encoding='utf-8') as f:
            json.dump(no_match, f, ensure_ascii=False)
    except OSError:
        pass

    # publicar: mismo pickle + catálogo en memoria del proceso
    with open(data_loader.CACHE_FILE, 'wb') as f:
        pickle.dump(catalogo, f)
    data_loader._productos = catalogo
    resumen['ok'] = True
    return resumen
