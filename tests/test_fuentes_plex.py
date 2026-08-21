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


def test_descripcion_incluye_la_presentacion():
    """El tamaño vive en medicamentos.Presentaci, no en Producto: sin él la app
    mostraba 'DOVE AC OLEO NUTRICION X' para el de 200ML y el de 400ML."""
    rows_prod = [{'sku': 1, 'descripcion': 'DOVE AC OLEO NUTRICION X',
                  'presentacion': '200ML', 'laboratorio': 'L', 'rubro': 'Perfumería', 'troquel': None}]
    r = transformar(rows_prod, [], [], [])
    assert r['productos']['1']['descripcion'] == 'DOVE AC OLEO NUTRICION X 200ML'


def test_descripcion_sin_presentacion_o_repetida():
    """Presentaci es NOT NULL DEFAULT '': con el campo vacío queda el nombre
    solo, y si el nombre ya termina con la presentación no se duplica."""
    assert fuentes_plex._descripcion('ZOLEPTIL', '') == 'ZOLEPTIL'
    assert fuentes_plex._descripcion('ZOLEPTIL', None) == 'ZOLEPTIL'
    assert fuentes_plex._descripcion('DOVE X 200ML', '200ml') == 'DOVE X 200ML'


def test_q_productos_trae_la_presentacion():
    """La columna es `Presentaci` (nombre truncado en el schema de Plex);
    `Presentacion`/`ProdPres` son de la tabla `productos` de Quantio, no de
    `medicamentos`."""
    assert 'm.Presentaci AS presentacion' in Q_PRODUCTOS


def test_q_ventas_suma_cant_decimal():
    """Las líneas fraccionadas (TipoCantidad='U') traen Cantidad en unidades
    sueltas; CantDecimal está SIEMPRE en cajas (verificado contra el informe
    manual 2026-07-06). Sumar Cantidad infla ×UnidadesPorCaja los fraccionados."""
    assert 'fl.CantDecimal' in Q_VENTAS
    assert '-fl.Cantidad ELSE fl.Cantidad' not in Q_VENTAS


def test_q_productos_filtra_ocultos_por_visible():
    """El catálogo de Plex trae ocultos/discontinuados. El campo `visible`
    (1=vigente, 0=oculto) es la señal correcta: verificado 2026-08-21 comparando
    los listados de Plex con/sin ocultos, el listado limpio son EXACTAMENTE los
    visible=1 (49.457, sin excepción)."""
    assert 'm.visible = 1' in Q_PRODUCTOS


def test_q_productos_no_filtra_solo_por_activo():
    """`Activo='S'` NO alcanza: dejaba pasar 54.535 ocultos (Activo='S' visible=0)
    y descartaba 99 vigentes (Activo='N' visible=1). Se filtra por visible, no Activo."""
    assert "m.Activo = 'S'" not in Q_PRODUCTOS


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
