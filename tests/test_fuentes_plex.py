import pytest

import fuentes_plex
from fuentes_plex import Q_PRODUCTOS, Q_VENTAS, transformar

CFG_REPLICA = {'host': 'replica', 'port': 3306, 'user': 'u', 'password': 'p', 'db': 'd'}
CFG_CONCENTRADOR = {'host': 'concentrador', 'port': 3306, 'user': 'u', 'password': 'p', 'db': 'd'}
CFG_VACIA = {'host': '', 'port': 3306, 'user': '', 'password': '', 'db': ''}


def test_transformar_arma_estructura():
    rows_prod = [
        {'sku': 555, 'descripcion': 'SHAMPOO X', 'laboratorio': 'LAB A', 'rubro': 'Perfumería', 'troquel': '1234567'},
        {'sku': 556, 'descripcion': 'CREMA Y', 'laboratorio': None, 'rubro': 'Accesorios', 'troquel': None},
    ]
    rows_eans = [{'sku': 555, 'ean': '7790000000001'}, {'sku': 999, 'ean': '779'}]
    rows_ventas = [
        {'sku': 555, 'sucursal': 2, 'unidades': 10},   # suc 2 = CERRO
        {'sku': 555, 'sucursal': 17, 'unidades': 99},  # excluida
        {'sku': 555, 'sucursal': 4040, 'unidades': 5}, # desconocida: se ignora
        {'sku': 777, 'sucursal': 2, 'unidades': 3},    # sku fuera de rubro: se ignora
    ]
    rows_stock = [{'sku': 556, 'sucursal': 6, 'cantidad': 4}]  # suc 6 = RECTA
    r = transformar(rows_prod, rows_eans, rows_ventas, rows_stock)
    assert r['productos']['555']['ean'] == '7790000000001'
    assert r['productos']['556']['ean'] == ''
    assert r['productos']['556']['laboratorio'] == ''
    assert r['ventas']['555'] == {'CERRO': 10}
    assert r['stock']['556'] == {'RECTA': 4}
    assert '777' not in r['ventas']


def test_q_ventas_suma_cant_decimal():
    """Las líneas fraccionadas (TipoCantidad='U') traen Cantidad en unidades
    sueltas; CantDecimal está SIEMPRE en cajas (verificado contra el informe
    manual 2026-07-06). Sumar Cantidad infla ×UnidadesPorCaja los fraccionados."""
    assert 'fl.CantDecimal' in Q_VENTAS
    assert '-fl.Cantidad ELSE fl.Cantidad' not in Q_VENTAS


def test_q_productos_filtra_discontinuados_por_activo():
    """El catálogo de Plex trae discontinuados; medicamentos.Activo='N' los
    marca. Sin este filtro entran a la app productos que ya no se reponen
    (verificado 2026-07-23: 40,7% del catálogo tenía Activo='N')."""
    assert "m.Activo = 'S'" in Q_PRODUCTOS


def test_q_productos_no_filtra_por_visible():
    """`visible` NO sirve como señal de vigencia: productos vigentes tienen
    visible=0 (verificado 2026-07-23 contra los SKU 3002602024 y 3002602032,
    ambos Activo='S' y visible=0). Filtrar por visible=1 los borraría."""
    assert 'visible' not in Q_PRODUCTOS


def test_transformar_ventas_decimales_truncan_a_cajas():
    """SUM(CantDecimal) devuelve float (16.5 cajas): se trunca a entero,
    igual que el informe manual."""
    rows_prod = [{'sku': 1, 'descripcion': 'P', 'laboratorio': 'L', 'rubro': 'Medicamentos', 'troquel': None}]
    r = transformar(rows_prod, [], [{'sku': 1, 'sucursal': 2, 'unidades': 16.5}], [])
    assert r['ventas']['1'] == {'CERRO': 16}


def test_ventas_negativas_no_rompen():
    rows_prod = [{'sku': 1, 'descripcion': 'P', 'laboratorio': 'L', 'rubro': 'Perfumería', 'troquel': None}]
    r = transformar(rows_prod, [], [{'sku': 1, 'sucursal': 2, 'unidades': -3}], [])
    assert r['ventas']['1'] == {'CERRO': -3}


def test_conn_usa_replica_si_anda(monkeypatch):
    """Con la réplica sana no se toca el concentrador."""
    intentos = []

    def fake_connect(cfg):
        intentos.append(cfg['host'])
        return 'CONN-REPLICA'

    monkeypatch.setattr(fuentes_plex, '_connect', fake_connect)
    monkeypatch.setattr(fuentes_plex, 'PLEX', CFG_REPLICA)
    monkeypatch.setattr(fuentes_plex, 'PLEX_FALLBACK', CFG_CONCENTRADOR)
    assert fuentes_plex._conn() == 'CONN-REPLICA'
    assert intentos == ['replica']
    assert fuentes_plex.origen_conexion() == 'replica'


def test_conn_cae_al_concentrador_si_replica_falla(monkeypatch):
    """Si el connect a la réplica falla y el concentrador (PLEX_FB_*) está
    configurado, conecta ahí y registra el origen para el aviso en admin."""
    intentos = []

    def fake_connect(cfg):
        intentos.append(cfg['host'])
        if cfg['host'] == 'replica':
            raise OSError('replica caida')
        return 'CONN-CONCENTRADOR'

    monkeypatch.setattr(fuentes_plex, '_connect', fake_connect)
    monkeypatch.setattr(fuentes_plex, 'PLEX', CFG_REPLICA)
    monkeypatch.setattr(fuentes_plex, 'PLEX_FALLBACK', CFG_CONCENTRADOR)
    assert fuentes_plex._conn() == 'CONN-CONCENTRADOR'
    assert intentos == ['replica', 'concentrador']
    assert fuentes_plex.origen_conexion() == 'concentrador'


def test_conn_sin_concentrador_configurado_propaga(monkeypatch):
    """Sin PLEX_FB_* configurado se propaga el error original (comportamiento
    actual: _cargar_con_memoria usa el last-good)."""
    def fake_connect(cfg):
        raise OSError('replica caida')

    monkeypatch.setattr(fuentes_plex, '_connect', fake_connect)
    monkeypatch.setattr(fuentes_plex, 'PLEX', CFG_REPLICA)
    monkeypatch.setattr(fuentes_plex, 'PLEX_FALLBACK', CFG_VACIA)
    with pytest.raises(OSError, match='replica caida'):
        fuentes_plex._conn()
