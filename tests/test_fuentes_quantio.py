from fuentes_quantio import matchear_cd

PRODUCTOS = {
    '555': {'ean': '7790000000001', 'troquel': '1234567'},
    '556': {'ean': '7790000000002', 'troquel': ''},
    '557': {'ean': '', 'troquel': '7654321'},
}


def test_cascada_codigo_directo():
    filas = [{'codigo': '555', 'ean': '', 'troquel': '', 'cantidad': 3}]
    stock, no_match = matchear_cd(filas, PRODUCTOS, {})
    assert stock == {'555': 3} and no_match == []


def test_cascada_ean():
    filas = [{'codigo': 'QX9', 'ean': '7790000000002', 'troquel': '', 'cantidad': 7}]
    stock, _ = matchear_cd(filas, PRODUCTOS, {})
    assert stock == {'556': 7}


def test_cascada_troquel():
    filas = [{'codigo': 'QX1', 'ean': '999', 'troquel': '7654321', 'cantidad': 2}]
    stock, _ = matchear_cd(filas, PRODUCTOS, {})
    assert stock == {'557': 2}


def test_cascada_mapeo_manual_y_no_match():
    filas = [
        {'codigo': 'QA', 'ean': '', 'troquel': '', 'cantidad': 5},
        {'codigo': 'QB', 'ean': '', 'troquel': '', 'cantidad': 1},
    ]
    stock, no_match = matchear_cd(filas, PRODUCTOS, {'QA': '555'})
    assert stock == {'555': 5}
    assert len(no_match) == 1 and no_match[0]['codigo'] == 'QB'


def test_cantidades_se_suman_y_cero_se_ignora():
    filas = [
        {'codigo': '555', 'ean': '', 'troquel': '', 'cantidad': 2},
        {'codigo': 'QX', 'ean': '7790000000001', 'troquel': '', 'cantidad': 3},
        {'codigo': '556', 'ean': '', 'troquel': '', 'cantidad': 0},
    ]
    stock, no_match = matchear_cd(filas, PRODUCTOS, {})
    assert stock == {'555': 5}
    assert no_match == []
