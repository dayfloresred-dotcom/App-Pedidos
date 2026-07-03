from datetime import datetime, timedelta

from fuentes_comparador import transformar


def _row(sku, drog, precio, hace_horas, alfabeta=None):
    return {'sku': sku, 'drogueria': drog, 'precio': precio,
            'cod_alfabeta': alfabeta,
            'consultado_at': datetime(2026, 7, 3, 12) - timedelta(hours=hace_horas)}


def test_transformar_mapea_dds_a_sud_y_frescura():
    ahora = datetime(2026, 7, 3, 12)
    rows = [
        _row('555', 'DDS', 100.5, 2, alfabeta='7654321'),
        _row('555', 'SUIZO', 120.0, 3),
        _row('556', 'SUIZO', 80.0, 5),
    ]
    r = transformar(rows, ahora)
    assert r['precios']['555'] == {'SUD': 100.5, 'SUIZO': 120.0}
    assert r['precios']['556'] == {'SUD': None, 'SUIZO': 80.0}
    assert r['alfabeta']['555'] == '7654321'
    assert r['stale'] is False


def test_stale_si_todo_viejo():
    ahora = datetime(2026, 7, 3, 12)
    r = transformar([_row('1', 'DDS', 10.0, 72)], ahora)
    assert r['stale'] is True


def test_vacio():
    r = transformar([], datetime(2026, 7, 3, 12))
    assert r['precios'] == {} and r['mas_reciente'] is None and r['stale'] is True


def test_transformar_con_datetimes_aware():
    from datetime import timezone
    ahora = datetime(2026, 7, 3, 12, tzinfo=timezone.utc)
    rows = [{'sku': '1', 'drogueria': 'DDS', 'precio': 10.0,
             'cod_alfabeta': None,
             'consultado_at': datetime(2026, 7, 3, 10, tzinfo=timezone.utc)}]
    r = transformar(rows, ahora)
    assert r['precios']['1']['SUD'] == 10.0
    assert r['stale'] is False


def test_fallback_por_ean_y_precio_con_descuento():
    ahora = datetime(2026, 7, 3, 12)
    rows = [
        {'sku': None, 'ean': '7790000000009', 'drogueria': 'DDS', 'precio': 55.5,
         'cod_alfabeta': '1112223', 'consultado_at': ahora},
        {'sku': '10', 'ean': '7790000000010', 'drogueria': 'SUIZO', 'precio': 20.0,
         'cod_alfabeta': None, 'consultado_at': ahora},
    ]
    r = transformar(rows, ahora)
    # sin sku: solo entra al mapa por EAN
    assert '7790000000009' in r['precios_ean']
    assert r['precios_ean']['7790000000009']['SUD'] == 55.5
    assert r['alfabeta_ean']['7790000000009'] == '1112223'
    # con sku: entra a ambos mapas
    assert r['precios']['10']['SUIZO'] == 20.0
    assert r['precios_ean']['7790000000010']['SUIZO'] == 20.0
