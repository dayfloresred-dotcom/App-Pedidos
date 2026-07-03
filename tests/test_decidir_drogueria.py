from data_loader import decidir_drogueria


def test_con_stock_cd_va_a_drogueria_red():
    d, mejor, ext, p_ext = decidir_drogueria(5, 100.0, 200.0)
    assert d == 'DROGUERIA RED'
    assert mejor is None
    assert ext == 'SUD' and p_ext == 100.0


def test_sin_cd_elige_mas_barata():
    assert decidir_drogueria(0, 100.0, 90.0) == ('SUIZO', 90.0, 'SUIZO', 90.0)
    assert decidir_drogueria(0, 80.0, 90.0) == ('SUD', 80.0, 'SUD', 80.0)


def test_empate_gana_sud():
    assert decidir_drogueria(0, 100.0, 100.0)[0] == 'SUD'


def test_solo_una_drogueria():
    assert decidir_drogueria(0, None, 50.0) == ('SUIZO', 50.0, 'SUIZO', 50.0)
    assert decidir_drogueria(0, 50.0, None) == ('SUD', 50.0, 'SUD', 50.0)


def test_sin_precios_queda_sin_drogueria():
    assert decidir_drogueria(0, None, None) == ('', None, '', None)
