import database


def test_estado_fuente_upsert_y_lectura():
    database.init_db()
    database.set_fuente_estado('plex', True, 21000, None)
    database.set_fuente_estado('plex', False, 0, 'timeout')
    estados = {e['fuente']: e for e in database.get_fuentes_estado()}
    assert estados['plex']['error'] == 'timeout'
    assert estados['plex']['ultima_ok'] is not None  # la ultima_ok NO se pisa al fallar


def test_mapeo_cd():
    database.init_db()
    n = database.agregar_mapeos_cd([('Q123', '555'), ('Q124', '556'), ('Q123', '999')])
    assert n == 3  # el tercero pisa al primero (upsert)
    m = database.get_mapeo_cd()
    assert m['Q123'] == '999' and m['Q124'] == '556'
