"""Vista de cumplimiento (admin): qué tan bien se responde a los pedidos.
get_cumplimiento agrega sobre solicitudes/items; la ruta la muestra."""
import pytest

import database
from config import now_local


@pytest.fixture()
def datos_cumplimiento(client):
    """2 solicitudes de CERRO: una comprada (hace 2 días de compra simulada),
    una pendiente sin procesar. Limpia al salir."""
    database.init_db()
    n1, id1 = database.crear_solicitud('CERRO', 'CERRO', [
        {'sku': 'CU1', 'descripcion': 'CUMPL COMPRADO', 'cantidad': 10}])
    n2, id2 = database.crear_solicitud('CERRO', 'CERRO', [
        {'sku': 'CU2', 'descripcion': 'CUMPL PENDIENTE', 'cantidad': 4}])
    conn = database.get_db()
    conn.execute("UPDATE solicitudes SET estado='comprado', fecha_compra=? WHERE id=?",
                 (now_local().strftime('%d/%m/%Y'), id1))
    conn.execute("UPDATE items_solicitud SET comprado=1 WHERE solicitud_id=?", (id1,))
    conn.commit()
    conn.close()
    yield {'ids': (id1, id2)}
    conn = database.get_db()
    for sid in (id1, id2):
        conn.execute('DELETE FROM items_solicitud WHERE solicitud_id=?', (sid,))
        conn.execute('DELETE FROM solicitudes WHERE id=?', (sid,))
    conn.commit()
    conn.close()


def test_get_cumplimiento_global_y_por_sucursal(datos_cumplimiento):
    r = database.get_cumplimiento(dias=None)
    g = r['global']
    assert g['solicitudes'] >= 2
    assert g['compradas'] >= 1
    assert g['pendientes'] >= 1
    assert 0 <= g['pct_compradas'] <= 100
    # compra de hoy: el promedio de días existe y es chico
    assert g['dias_promedio_compra'] is not None and g['dias_promedio_compra'] >= 0

    cerro = next(s for s in r['por_sucursal'] if s['sucursal'] == 'CERRO')
    assert cerro['pedido_u'] >= 14          # 10 + 4
    assert cerro['atendido_u'] >= 10        # el comprado
    assert cerro['pendiente_u'] >= 4        # el pendiente
    assert 0 <= cerro['pct'] <= 100


def test_get_cumplimiento_demorados(datos_cumplimiento):
    r = database.get_cumplimiento(dias=None)
    dem = next((d for d in r['demorados'] if d['sku'] == 'CU2'), None)
    assert dem is not None
    assert dem['cantidad'] == 4
    assert dem['dias'] >= 0
    assert 'CERRO' in dem['sucursales']
    assert 'desde' not in dem  # campo interno: no debe filtrarse (date no es JSON-serializable)
    # el comprado NO aparece como demorado
    assert not any(d['sku'] == 'CU1' for d in r['demorados'])


def test_ruta_cumplimiento_admin(admin, datos_cumplimiento):
    r = admin.get('/cumplimiento')
    assert r.status_code == 200
    assert b'CUMPL PENDIENTE' in r.data


def test_ruta_cumplimiento_niega_sucursal(sucursal):
    r = sucursal.get('/cumplimiento', follow_redirects=False)
    assert r.status_code in (302, 403)
