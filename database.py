import sqlite3
from datetime import datetime
from config import DB_PATH

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
    fecha  = datetime.now().strftime('%d/%m/%Y %H:%M')
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
    query = 'SELECT s.*, COUNT(i.id) as n_items FROM solicitudes s LEFT JOIN items_solicitud i ON i.solicitud_id=s.id'
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
        WHERE s.estado='pendiente'
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
        WHERE i.sku=? AND s.estado='pendiente'
        ORDER BY s.sucursal
    ''', (sku,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

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

def cancelar_solicitud(sol_id):
    conn = get_db()
    conn.execute(
        'UPDATE solicitudes SET estado=? WHERE id=? AND estado=?',
        ('cancelado', sol_id, 'pendiente')
    )
    conn.commit()
    conn.close()
