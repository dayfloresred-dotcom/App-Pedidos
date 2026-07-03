import json
import os

import fuentes
from data_loader import decidir_drogueria


PLEX = {
    'productos': {
        '555': {'descripcion': 'SHAMPOO X', 'laboratorio': 'LAB A', 'rubro': 'Perfumería',
                'ean': '7790000000001', 'troquel': '1111111'},
        '556': {'descripcion': 'CREMA Y', 'laboratorio': 'LAB B', 'rubro': 'Accesorios',
                'ean': '7790000000002', 'troquel': ''},
    },
    'ventas': {'555': {'CERRO': 10, 'RECTA': 2}},
    'stock':  {'555': {'CERRO': 4}, '556': {'RECTA': 1}},
}
PRECIOS = {'precios': {'555': {'SUD': 100.0, 'SUIZO': 90.0}},
           'alfabeta': {'555': '7654321'}, 'mas_reciente': None, 'stale': False}


def test_construir_catalogo_estructura_identica():
    cat = fuentes.construir_catalogo(PLEX, PRECIOS, {'556': 8})
    por_sku = {p['sku']: p for p in cat}
    p = por_sku['555']
    # exactamente los campos que produce load_productos()
    assert set(p.keys()) == {'sku', 'ean', 'descripcion', 'laboratorio', 'rubro',
                             'stock_cd', 'drogueria', 'mejor_precio', 'drog_ext',
                             'troquel', 'troquel_pres', 'necesidad', 'stock_real', 'ventas'}
    assert p['drogueria'] == 'SUIZO' and p['mejor_precio'] == 90.0  # sin stock CD, mas barata
    assert p['troquel'] == '7654321'       # alfabeta del comparador -> export .dds
    assert p['troquel_pres'] == '1111111'  # troquel de Plex -> export Quantio
    assert p['necesidad'] == {'CERRO': 6, 'RECTA': 2}  # ventas - stock, min 0
    assert p['stock_real'] == {'CERRO': 4, 'RECTA': 0}
    assert por_sku['556']['stock_cd'] == 8
    assert por_sku['556']['drogueria'] == 'DROGUERIA RED'
    assert por_sku['556']['drogueria'] == 'DROGUERIA RED'
    assert por_sku['556']['mejor_precio'] is None


def test_refrescar_con_memoria_por_fuente(monkeypatch, tmp_path):
    llamadas = {'n': 0}

    def plex_ok():
        return PLEX

    def comparador_falla():
        llamadas['n'] += 1
        raise RuntimeError('conexion rechazada')

    monkeypatch.setattr(fuentes, '_DIR_MEMORIA', str(tmp_path))
    monkeypatch.setattr('fuentes_plex.configurada', lambda: True)
    monkeypatch.setattr('fuentes_plex.cargar', plex_ok)
    monkeypatch.setattr('fuentes_comparador.configurada', lambda: True)
    monkeypatch.setattr('fuentes_comparador.cargar', lambda: PRECIOS)
    monkeypatch.setattr('fuentes_quantio.configurada', lambda: False)

    r1 = fuentes.refrescar_fuentes()
    assert r1['ok'] is True and r1['productos'] == 2
    assert r1['fuentes']['comparador']['ok'] is True

    # ahora el comparador falla: usa la memoria last-good
    monkeypatch.setattr('fuentes_comparador.cargar', comparador_falla)
    r2 = fuentes.refrescar_fuentes()
    assert r2['ok'] is True
    assert r2['fuentes']['comparador']['ok'] is False
    assert r2['fuentes']['comparador']['desde_memoria'] is True
    assert r2['productos'] == 2  # catalogo igual se armo


def test_refrescar_falla_si_fuente_critica_sin_memoria(monkeypatch, tmp_path):
    monkeypatch.setattr(fuentes, '_DIR_MEMORIA', str(tmp_path))
    monkeypatch.setattr('fuentes_plex.configurada', lambda: True)
    monkeypatch.setattr('fuentes_plex.cargar',
                        lambda: (_ for _ in ()).throw(RuntimeError('down')))
    monkeypatch.setattr('fuentes_comparador.configurada', lambda: True)
    monkeypatch.setattr('fuentes_comparador.cargar', lambda: PRECIOS)
    monkeypatch.setattr('fuentes_quantio.configurada', lambda: False)
    r = fuentes.refrescar_fuentes()
    assert r['ok'] is False
    assert 'down' in (r['fuentes']['plex']['error'] or '')
