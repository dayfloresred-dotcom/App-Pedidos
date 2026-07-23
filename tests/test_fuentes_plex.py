from fuentes_plex import Q_PRODUCTOS, Q_VENTAS, transformar


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
