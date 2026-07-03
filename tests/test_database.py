import os
import sqlite3

import database


def test_init_db_crea_indices():
    database.init_db()
    conn = sqlite3.connect(os.environ['PEDIDOS_DB_PATH'])
    nombres = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index'")}
    conn.close()
    for idx in ['idx_items_sku', 'idx_items_solicitud',
                'idx_envios_suc_sku', 'idx_omitidos_suc_sku']:
        assert idx in nombres, idx
