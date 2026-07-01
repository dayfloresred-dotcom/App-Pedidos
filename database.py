import sqlite3
from datetime import datetime
from config import DB_PATH, now_local

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            rol           TEXT NOT NULL CHECK(rol IN ('sucursal','admin'))
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS solicitudes (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            numero           TEXT UNIQUE NOT NULL,
            sucursal         TEXT NOT NULL,
            creado_por       TEXT NOT NULL,
            fecha_solicitud  TEXT NOT NULL,
            fecha_compra     TEXT,
            estado           TEXT NOT NULL DEFAULT 'pendiente'
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS items_solicitud (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            solicitud_id  INTEGER NOT NULL REFERENCES solicitudes(id),
            sku           TEXT NOT NULL,
            ean           TEXT,
            descripcion   TEXT NOT NULL,
            laboratorio   TEXT,
            cantidad      INTEGER NOT NULL,
            drogueria     TEXT
        )
    ''')
    # Migración: columnas para seguimiento de orden generada / cancelación por ítem
    cols = {r['name'] for r in conn.execute("PRAGMA table_info(items_solicitud)").fetchall()}
    if 'ordenado' not in cols:
        conn.execute("ALTER TABLE items_solicitud ADD COLUMN ordenado INTEGER NOT NULL DEFAULT 0")
    if 'drogueria_final' not in cols:
        conn.execute("ALTER TABLE items_solicitud ADD COLUMN drogueria_final TEXT")
    if 'fecha_orden' not in cols:
        conn.execute("ALTER TABLE items_solicitud ADD COLUMN fecha_orden TEXT")
    if 'cancelado' not in cols:
        conn.execute("ALTER TABLE items_solicitud ADD COLUMN cancelado INTEGER NOT NULL DEFAULT 0")
    if 'comprado' not in cols:
        conn.execute("ALTER TABLE items_solicitud ADD COLUMN comprado INTEGER NOT NULL DEFAULT 0")
    conn.execute('''
        CREATE TABLE IF NOT EXISTS envios (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            sucursal  TEXT NOT NULL,
            sku       TEXT NOT NULL,
            drogueria TEXT NOT NULL,
            cantidad  INTEGER NOT NULL,
            UNIQUE(sucursal, sku, drogueria)
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS omitidos (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            sucursal  TEXT NOT NULL,
            sku       TEXT NOT NULL,
            drogueria TEXT NOT NULL,
            UNIQUE(sucursal, sku, drogueria)
        )
    ''')
    conn.commit()
    conn.close()

def generar_numero():
    conn = get_db()
    row = conn.execute('SELECT COUNT(*) as c FROM solicitudes').fetchone()
    n = row['c'] + 1
    conn.close()
    return f'SOL-{n:06d}'

def crear_solicitud(sucursal, creado_por, items):
    conn = get_db()
    numero = generar_numero()
    fecha  = now_local().strftime('%d/%m/%Y %H:%M')
    conn.execute(
        'INSERT INTO solicitudes (numero, sucursal, creado_por, fecha_solicitud) VALUES (?,?,?,?)',
        (numero, sucursal, creado_por, fecha)
    )
    sol_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
    for it in items:
        conn.execute(
            'INSERT INTO items_solicitud (solicitud_id, sku, ean, descripcion, laboratorio, cantidad, drogueria) VALUES (?,?,?,?,?,?,?)',
            (sol_id, it['sku'], it.get('ean',''), it['descripcion'], it.get('laboratorio',''), it['cantidad'], it.get('drogueria',''))
        )
    conn.commit()
    conn.close()
    return numero, sol_id

def get_solicitudes_sucursal(sucursal):
    conn = get_db()
    rows = conn.execute(
        'SELECT * FROM solicitudes WHERE sucursal=? ORDER BY id DESC', (sucursal,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_solicitud_detalle(sol_id):
    conn = get_db()
    sol   = conn.execute('SELECT * FROM solicitudes WHERE id=?', (sol_id,)).fetchone()
    items = conn.execute('SELECT * FROM items_solicitud WHERE solicitud_id=?', (sol_id,)).fetchall()
    conn.close()
    if not sol:
        return None, []
    return dict(sol), [dict(i) for i in items]

def get_todas_solicitudes(sucursal_filtro=None, lab_filtro=None, drogueria_filtro=None):
    conn = get_db()
    query = 'SELECT s.*, COUNT(i.id) as n_items FROM solicitudes s LEFT JOIN items_solicitud i ON i.solicitud_id=s.id AND i.cancelado=0'
    params = []
    wheres = []
    if sucursal_filtro:
        wheres.append('s.sucursal=?'); params.append(sucursal_filtro)
    if wheres:
        query += ' WHERE ' + ' AND '.join(wheres)
    query += ' GROUP BY s.id ORDER BY s.id DESC'
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_consolidado(sucursal_filtro=None, lab_filtro=None, drogueria_filtro=None):
    conn = get_db()
    query = '''
        SELECT i.sku, i.ean, i.descripcion, i.laboratorio, i.drogueria,
               SUM(i.cantidad) as total,
               GROUP_CONCAT(DISTINCT s.sucursal) as sucursales
        FROM items_solicitud i
        JOIN solicitudes s ON s.id=i.solicitud_id
        WHERE s.estado='pendiente' AND i.cancelado=0 AND i.comprado=0
    '''
    params = []
    if sucursal_filtro:
        query += ' AND s.sucursal=?'; params.append(sucursal_filtro)
    if lab_filtro:
        query += ' AND LOWER(i.laboratorio) LIKE ?'; params.append(f'%{lab_filtro.lower()}%')
    if drogueria_filtro:
        query += ' AND i.drogueria=?'; params.append(drogueria_filtro)
    query += ' GROUP BY i.sku ORDER BY total DESC'
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_detalle_por_sucursal(sku):
    conn = get_db()
    rows = conn.execute('''
        SELECT s.sucursal, i.cantidad
        FROM items_solicitud i
        JOIN solicitudes s ON s.id=i.solicitud_id
        WHERE i.sku=? AND s.estado='pendiente' AND i.cancelado=0 AND i.comprado=0
        ORDER BY s.sucursal
    ''', (sku,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_items_detalle(sku):
    """Detalle por sucursal de un producto pendiente, con estado de orden.
    ordenado=1 solo si TODOS los ítems de esa sucursal+sku están generados."""
    conn = get_db()
    rows = conn.execute('''
        SELECT s.sucursal,
               SUM(i.cantidad)        as cantidad,
               MIN(i.ordenado)        as ordenado,
               MAX(i.drogueria_final) as drogueria_final
        FROM items_solicitud i
        JOIN solicitudes s ON s.id = i.solicitud_id
        WHERE i.sku=? AND s.estado='pendiente' AND i.cancelado=0 AND i.comprado=0
        GROUP BY s.sucursal
        ORDER BY s.sucursal
    ''', (sku,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def marcar_item_generado(sku, sucursal, drogueria, fecha):
    """Marca como generado el pedido de un producto para una sucursal puntual."""
    conn = get_db()
    conn.execute('''
        UPDATE items_solicitud SET ordenado=1, drogueria_final=?, fecha_orden=?
        WHERE sku=? AND cancelado=0 AND comprado=0 AND solicitud_id IN (
            SELECT id FROM solicitudes WHERE sucursal=? AND estado='pendiente'
        )
    ''', (drogueria, fecha, sku, sucursal))
    conn.commit()
    conn.close()

def desmarcar_item_generado(sku, sucursal):
    conn = get_db()
    conn.execute('''
        UPDATE items_solicitud SET ordenado=0, drogueria_final=NULL, fecha_orden=NULL
        WHERE sku=? AND solicitud_id IN (
            SELECT id FROM solicitudes WHERE sucursal=? AND estado='pendiente'
        )
    ''', (sku, sucursal))
    conn.commit()
    conn.close()

def _recalc_estado_solicitud(conn, sol_id):
    """Recalcula el estado de la solicitud segun sus items:
    - todos cancelados -> 'cancelado'
    - todos los activos (no cancelados) comprados -> 'comprado' (con fecha)"""
    rows = conn.execute("SELECT cancelado, comprado FROM items_solicitud WHERE solicitud_id=?", (sol_id,)).fetchall()
    if not rows:
        return
    if all(r['cancelado'] for r in rows):
        conn.execute("UPDATE solicitudes SET estado='cancelado' WHERE id=? AND estado!='cancelado'", (sol_id,))
        return
    activos = [r for r in rows if not r['cancelado']]
    if activos and all(r['comprado'] for r in activos):
        fecha = now_local().strftime('%d/%m/%Y')
        conn.execute("UPDATE solicitudes SET estado='comprado', fecha_compra=? WHERE id=? AND estado='pendiente'", (fecha, sol_id))
    elif activos and any(not r['comprado'] for r in activos):
        conn.execute("UPDATE solicitudes SET estado='pendiente', fecha_compra=NULL WHERE id=? AND estado='comprado'", (sol_id,))

def cancelar_producto(sku):
    """Cancela un producto para TODAS las sucursales con pedido pendiente."""
    conn = get_db()
    sols = [r['id'] for r in conn.execute('''
        SELECT DISTINCT s.id FROM solicitudes s JOIN items_solicitud i ON i.solicitud_id=s.id
        WHERE i.sku=? AND s.estado='pendiente'
    ''', (sku,)).fetchall()]
    conn.execute('''
        UPDATE items_solicitud SET cancelado=1
        WHERE sku=? AND solicitud_id IN (SELECT id FROM solicitudes WHERE estado='pendiente')
    ''', (sku,))
    for sid in sols:
        _recalc_estado_solicitud(conn, sid)
    conn.commit()
    conn.close()

def cancelar_producto_sucursal(sku, sucursal):
    """Cancela un producto para una sucursal puntual."""
    conn = get_db()
    sols = [r['id'] for r in conn.execute(
        "SELECT id FROM solicitudes WHERE sucursal=? AND estado='pendiente'", (sucursal,)
    ).fetchall()]
    conn.execute('''
        UPDATE items_solicitud SET cancelado=1
        WHERE sku=? AND solicitud_id IN (
            SELECT id FROM solicitudes WHERE sucursal=? AND estado='pendiente'
        )
    ''', (sku, sucursal))
    for sid in sols:
        _recalc_estado_solicitud(conn, sid)
    conn.commit()
    conn.close()

def cancelar_item(item_id):
    """Cancela un ítem puntual (un producto dentro de un pedido). Devuelve solicitud_id o None."""
    conn = get_db()
    row = conn.execute("SELECT solicitud_id FROM items_solicitud WHERE id=?", (item_id,)).fetchone()
    if not row:
        conn.close()
        return None
    conn.execute("UPDATE items_solicitud SET cancelado=1 WHERE id=?", (item_id,))
    _recalc_estado_solicitud(conn, row['solicitud_id'])
    conn.commit()
    conn.close()
    return row['solicitud_id']

def restaurar_item(item_id):
    """Descancela un ítem: vuelve a pendiente y reaparece en Generar orden."""
    conn = get_db()
    row = conn.execute("SELECT solicitud_id FROM items_solicitud WHERE id=?", (item_id,)).fetchone()
    if not row:
        conn.close()
        return None
    conn.execute("UPDATE items_solicitud SET cancelado=0 WHERE id=?", (item_id,))
    conn.execute("UPDATE solicitudes SET estado='pendiente', fecha_compra=NULL WHERE id=? AND estado='cancelado'", (row['solicitud_id'],))
    conn.commit()
    conn.close()
    return row['solicitud_id']

def get_item_sucursal(item_id):
    conn = get_db()
    row = conn.execute('''
        SELECT s.sucursal FROM items_solicitud i JOIN solicitudes s ON s.id=i.solicitud_id WHERE i.id=?
    ''', (item_id,)).fetchone()
    conn.close()
    return row['sucursal'] if row else None

def marcar_comprado(sol_ids, fecha_compra):
    conn = get_db()
    for sid in sol_ids:
        conn.execute(
            'UPDATE solicitudes SET estado=?, fecha_compra=? WHERE id=?',
            ('comprado', fecha_compra, sid)
        )
    conn.commit()
    conn.close()

def actualizar_droguerias_pendientes(prod_map):
    """Actualiza droguería de todos los items pendientes según datos nuevos.
    prod_map: dict sku -> producto (de load_productos)
    Retorna cantidad de items actualizados.
    """
    conn = get_db()
    rows = conn.execute('''
        SELECT DISTINCT i.sku FROM items_solicitud i
        JOIN solicitudes s ON s.id = i.solicitud_id
        WHERE s.estado = 'pendiente'
    ''').fetchall()
    updated = 0
    for row in rows:
        sku  = row['sku']
        prod = prod_map.get(sku)
        if prod:
            conn.execute('''
                UPDATE items_solicitud SET drogueria=?
                WHERE sku=? AND solicitud_id IN (
                    SELECT id FROM solicitudes WHERE estado='pendiente'
                )
            ''', (prod['drogueria'], sku))
            updated += 1
    conn.commit()
    conn.close()
    return updated

def marcar_comprado_drogueria(drogueria, fecha):
    """Marca como comprados (a nivel item) los productos de UNA droguería; las demás quedan pendientes."""
    code = 'CD' if drogueria == 'DROGUERIA RED' else drogueria
    conn = get_db()
    sols = [r['id'] for r in conn.execute('''
        SELECT DISTINCT s.id FROM solicitudes s JOIN items_solicitud i ON i.solicitud_id=s.id
        WHERE i.drogueria=? AND s.estado='pendiente' AND i.cancelado=0 AND i.comprado=0
    ''', (drogueria,)).fetchall()]
    conn.execute('''
        UPDATE items_solicitud SET comprado=1, ordenado=1, drogueria_final=?, fecha_orden=?
        WHERE drogueria=? AND cancelado=0 AND comprado=0
          AND solicitud_id IN (SELECT id FROM solicitudes WHERE estado='pendiente')
    ''', (code, fecha, drogueria))
    n = conn.total_changes
    for sid in sols:
        _recalc_estado_solicitud(conn, sid)
    conn.commit()
    conn.close()
    return n

def marcar_inexistente(sku):
    """Marca un producto sin precio como inexistente: cancelado + origen 'INEXISTENTE'."""
    conn = get_db()
    sols = [r['id'] for r in conn.execute('''
        SELECT DISTINCT s.id FROM solicitudes s JOIN items_solicitud i ON i.solicitud_id=s.id
        WHERE i.sku=? AND s.estado='pendiente' AND i.cancelado=0
    ''', (sku,)).fetchall()]
    conn.execute('''
        UPDATE items_solicitud SET cancelado=1, drogueria_final='INEXISTENTE'
        WHERE sku=? AND cancelado=0 AND solicitud_id IN (SELECT id FROM solicitudes WHERE estado='pendiente')
    ''', (sku,))
    for sid in sols:
        _recalc_estado_solicitud(conn, sid)
    conn.commit()
    conn.close()

def registrar_envio(sucursal, sku, drogueria, cantidad):
    """Registra (o actualiza) cuántas unidades se envían de un producto a una sucursal desde una droguería."""
    conn = get_db()
    try:
        cant = int(cantidad)
    except (TypeError, ValueError):
        cant = 0
    if cant > 0:
        conn.execute('''INSERT INTO envios (sucursal, sku, drogueria, cantidad) VALUES (?,?,?,?)
            ON CONFLICT(sucursal, sku, drogueria) DO UPDATE SET cantidad=excluded.cantidad''',
            (sucursal, sku, drogueria, cant))
    else:
        conn.execute("DELETE FROM envios WHERE sucursal=? AND sku=? AND drogueria=?", (sucursal, sku, drogueria))
    conn.commit()
    conn.close()

def get_envios(sucursal, sku):
    conn = get_db()
    rows = conn.execute("SELECT drogueria, cantidad FROM envios WHERE sucursal=? AND sku=?", (sucursal, sku)).fetchall()
    conn.close()
    return {r['drogueria']: r['cantidad'] for r in rows}

def get_envios_por_drogueria(drogueria):
    """Suma de unidades enviadas por producto desde una droguería (para el export)."""
    conn = get_db()
    rows = conn.execute(
        "SELECT sku, SUM(cantidad) AS tot FROM envios WHERE drogueria=? GROUP BY sku HAVING tot>0",
        (drogueria,)
    ).fetchall()
    conn.close()
    return [{'sku': r['sku'], 'total': r['tot']} for r in rows]

def get_envios_sucursal(sucursal):
    conn = get_db()
    rows = conn.execute("SELECT sku, drogueria, cantidad FROM envios WHERE sucursal=?", (sucursal,)).fetchall()
    conn.close()
    out = {}
    for r in rows:
        out.setdefault(r['sku'], {})[r['drogueria']] = r['cantidad']
    return out

def actualizar_comprado_por_envio(sucursal, sku):
    """Si lo enviado (todas las droguerías + rotación) cubre lo solicitado por la sucursal,
    marca esos ítems como comprados (=> 'Pedido realizado'). Si no alcanza, lo revierte."""
    conn = get_db()
    req = conn.execute("""
        SELECT COALESCE(SUM(i.cantidad),0) FROM items_solicitud i
        JOIN solicitudes s ON s.id=i.solicitud_id
        WHERE i.sku=? AND s.sucursal=? AND s.estado IN ('pendiente','comprado') AND i.cancelado=0
    """, (sku, sucursal)).fetchone()[0]
    sent = conn.execute("SELECT COALESCE(SUM(cantidad),0) FROM envios WHERE sucursal=? AND sku=?",
                        (sucursal, sku)).fetchone()[0]
    fecha = now_local().strftime('%d/%m/%Y')
    cubierto = 1 if (req > 0 and sent >= req) else 0
    conn.execute("""
        UPDATE items_solicitud SET comprado=?, fecha_orden=?
        WHERE sku=? AND cancelado=0 AND solicitud_id IN (
            SELECT id FROM solicitudes WHERE sucursal=? AND estado IN ('pendiente','comprado')
        )
    """, (cubierto, fecha if cubierto else None, sku, sucursal))
    sols = [r['solicitud_id'] for r in conn.execute("""
        SELECT DISTINCT i.solicitud_id FROM items_solicitud i
        JOIN solicitudes s ON s.id=i.solicitud_id WHERE i.sku=? AND s.sucursal=?
    """, (sku, sucursal)).fetchall()]
    for sid in sols:
        _recalc_estado_solicitud(conn, sid)
    conn.commit()
    conn.close()

def get_envios_sucursal_drogueria(sucursal, drogueria):
    """Unidades enviadas de cada producto a una sucursal desde una droguería (para export por sucursal)."""
    conn = get_db()
    rows = conn.execute(
        "SELECT sku, cantidad FROM envios WHERE sucursal=? AND drogueria=? AND cantidad>0",
        (sucursal, drogueria)
    ).fetchall()
    conn.close()
    return [{'sku': r['sku'], 'cantidad': r['cantidad']} for r in rows]

def omitir_drogueria(sucursal, sku, drogueria):
    """Marca que un producto NO se pide de esa droguería para esa sucursal (se oculta de esa tarjeta)."""
    conn = get_db()
    conn.execute("INSERT OR IGNORE INTO omitidos (sucursal, sku, drogueria) VALUES (?,?,?)",
                 (sucursal, sku, drogueria))
    conn.commit()
    conn.close()

def omitir_producto(sku, drogueria):
    """Quita un producto de una droguería para TODAS sus sucursales pendientes."""
    conn = get_db()
    sucs = [r['sucursal'] for r in conn.execute(
        "SELECT DISTINCT s.sucursal FROM items_solicitud i JOIN solicitudes s ON s.id=i.solicitud_id "
        "WHERE i.sku=? AND s.estado='pendiente' AND i.cancelado=0", (sku,)).fetchall()]
    for suc in sucs:
        conn.execute("INSERT OR IGNORE INTO omitidos (sucursal, sku, drogueria) VALUES (?,?,?)",
                     (suc, sku, drogueria))
    conn.commit()
    conn.close()

def quitar_omitido(sucursal, sku, drogueria):
    conn = get_db()
    conn.execute("DELETE FROM omitidos WHERE sucursal=? AND sku=? AND drogueria=?",
                 (sucursal, sku, drogueria))
    conn.commit()
    conn.close()

def get_omitidos_sucursal(sucursal):
    conn = get_db()
    rows = conn.execute("SELECT sku, drogueria FROM omitidos WHERE sucursal=?", (sucursal,)).fetchall()
    conn.close()
    out = {}
    for r in rows:
        out.setdefault(r['sku'], set()).add(r['drogueria'])
    return out

def cancelar_solicitud(sol_id):
    conn = get_db()
    conn.execute(
        'UPDATE solicitudes SET estado=? WHERE id=? AND estado=?',
        ('cancelado', sol_id, 'pendiente')
    )
    conn.commit()
    conn.close()
