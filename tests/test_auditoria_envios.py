"""Auditoría de envíos: cada envío registra cuándo y quién lo hizo
(base para la vista de cumplimiento y para reconstruir discusiones
de 'esto nunca llegó')."""
import database


def _limpiar(sucursal, sku):
    conn = database.get_db()
    conn.execute('DELETE FROM envios WHERE sucursal=? AND sku=?', (sucursal, sku))
    conn.commit()
    conn.close()


def test_registrar_envio_guarda_fecha_y_usuario():
    database.init_db()
    _limpiar('CERRO', 'AUD1')
    database.registrar_envio('CERRO', 'AUD1', 'SUD', 3, usuario='admin')
    env = database.get_db().execute(
        "SELECT * FROM envios WHERE sucursal='CERRO' AND sku='AUD1'").fetchone()
    assert env['cantidad'] == 3
    assert env['usuario'] == 'admin'
    assert env['fecha'] and '/' in env['fecha']  # dd/mm/yyyy HH:MM
    _limpiar('CERRO', 'AUD1')


def test_upsert_actualiza_fecha_y_usuario():
    database.init_db()
    _limpiar('RECTA', 'AUD2')
    database.registrar_envio('RECTA', 'AUD2', 'CD', 1, usuario='admin')
    database.registrar_envio('RECTA', 'AUD2', 'CD', 5, usuario='otroadmin')
    env = database.get_db().execute(
        "SELECT * FROM envios WHERE sucursal='RECTA' AND sku='AUD2'").fetchone()
    assert env['cantidad'] == 5
    assert env['usuario'] == 'otroadmin'
    _limpiar('RECTA', 'AUD2')


def test_usuario_es_opcional_compat():
    """Llamadas sin usuario siguen funcionando (compat con código existente)."""
    database.init_db()
    _limpiar('URCA', 'AUD3')
    database.registrar_envio('URCA', 'AUD3', 'SUIZO', 2)
    env = database.get_db().execute(
        "SELECT * FROM envios WHERE sucursal='URCA' AND sku='AUD3'").fetchone()
    assert env['cantidad'] == 2 and env['fecha']
    _limpiar('URCA', 'AUD3')
