from fuentes_plex import transformar


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


def test_ventas_negativas_no_rompen():
    rows_prod = [{'sku': 1, 'descripcion': 'P', 'laboratorio': 'L', 'rubro': 'Perfumería', 'troquel': None}]
    r = transformar(rows_prod, [], [{'sku': 1, 'sucursal': 2, 'unidades': -3}], [])
    assert r['ventas']['1'] == {'CERRO': -3}
