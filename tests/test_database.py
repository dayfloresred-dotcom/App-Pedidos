import os
import sqlite3

import database


def test_generar_numero_no_reusa_tras_borrado():
    """COUNT(*)+1 reusa números si se borran filas: tras borrar una solicitud
    vieja, la próxima creación chocaba con el UNIQUE de numero. El número debe
    derivar del MAX existente, no del count."""
    database.init_db()
    conn = database.get_db()
    existentes = {r['numero'] for r in conn.execute('SELECT numero FROM solicitudes')}
    conn.close()

    n1, id1 = database.crear_solicitud('CERRO', 'CERRO', [
        {'sku': 'T1', 'descripcion': 'TEST UNO', 'cantidad': 1}])
    n2, id2 = database.crear_solicitud('CERRO', 'CERRO', [
        {'sku': 'T2', 'descripcion': 'TEST DOS', 'cantidad': 1}])

    conn = database.get_db()
    conn.execute('DELETE FROM items_solicitud WHERE solicitud_id=?', (id1,))
    conn.execute('DELETE FROM solicitudes WHERE id=?', (id1,))
    conn.commit()
    conn.close()

    # Con COUNT+1 esto levantaba IntegrityError (recalcula el número de n2)
    n3, id3 = database.crear_solicitud('CERRO', 'CERRO', [
        {'sku': 'T3', 'descripcion': 'TEST TRES', 'cantidad': 1}])
    assert n3 not in existentes | {n1, n2}

    conn = database.get_db()
    for sid in (id2, id3):
        conn.execute('DELETE FROM items_solicitud WHERE solicitud_id=?', (sid,))
        conn.execute('DELETE FROM solicitudes WHERE id=?', (sid,))
    conn.commit()
    conn.close()


def test_init_db_crea_indices():
    database.init_db()
    conn = sqlite3.connect(os.environ['PEDIDOS_DB_PATH'])
    nombres = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index'")}
    conn.close()
    for idx in ['idx_items_sku', 'idx_items_solicitud',
                'idx_envios_suc_sku', 'idx_omitidos_suc_sku']:
        assert idx in nombres, idx
