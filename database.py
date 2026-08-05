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
    if 'observacion' not in cols:
        conn.execute("ALTER TABLE items_solicitud ADD COLUMN observacion TEXT")
    if 'sin_necesidad' not in cols:
        conn.execute("ALTER TABLE items_solicitud ADD COLUMN sin_necesidad INTEGER NOT NULL DEFAULT 0")
    conn.execute('''
        CREATE TABLE IF NOT EXISTS carrito (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            sucursal    TEXT NOT NULL,
            sku         TEXT NOT NULL,
            ean         TEXT,
            descripcion TEXT,
            laboratorio TEXT,
            drogueria   TEXT,
            cantidad    INTEGER NOT NULL,
            observacion TEXT,
            UNIQUE(sucursal, sku)
        )
    ''')
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
    # Migración: auditoría de envíos (quién y cuándo; filas viejas quedan NULL)
    cols_env = {r['name'] for r in conn.execute("PRAGMA table_info(envios)").fetchall()}
    if 'fecha' not in cols_env:
        conn.execute("ALTER TABLE envios ADD COLUMN fecha TEXT")
    if 'usuario' not in cols_env:
        conn.execute("ALTER TABLE envios ADD COLUMN usuario TEXT")
    if 'exportado' not in cols_env:
        conn.execute("ALTER TABLE envios ADD COLUMN exportado INTEGER NOT NULL DEFAULT 0")
    conn.execute('''
        CREATE TABLE IF NOT EXISTS omitidos (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            sucursal  TEXT NOT NULL,
            sku       TEXT NOT NULL,
            drogueria TEXT NOT NULL,
            UNIQUE(sucursal, sku, drogueria)
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS fuentes_estado (
            fuente      TEXT PRIMARY KEY,
            ultima_ok   TEXT,
            filas       INTEGER NOT NULL DEFAULT 0,
            error       TEXT,
            actualizado TEXT
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS mapeo_cd (
            codigo_quantio TEXT PRIMARY KEY,
            sku            TEXT NOT NULL
        )
    ''')
    # Índices: aceleran get_consolidado / get_items_detalle / get_envios,
    # que se ejecutan por producto en cada render de Generar orden.
    conn.execute("CREATE INDEX IF NOT EXISTS idx_items_sku ON items_solicitud(sku)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_items_solicitud ON items_solicitud(solicitud_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_envios_suc_sku ON envios(sucursal, sku)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_omitidos_suc_sku ON omitidos(sucursal, sku)")
    conn.commit()
    conn.close()

def generar_numero(conn=None):
    """Próximo número: MAX existente + 1. (COUNT(*)+1 reusaba números tras un
    borrado y duplicaba bajo escrituras concurrentes; numero es UNIQUE.)"""
    propia = conn is None
    if propia:
        conn = get_db()
    row = conn.execute(
        "SELECT COALESCE(MAX(CAST(substr(numero, 5) AS INTEGER)), 0) AS m FROM solicitudes"
    ).fetchone()
    if propia:
        conn.close()
    return f"SOL-{row['m'] + 1:06d}"

def crear_solicitud(sucursal, creado_por, items):
    conn = get_db()
    fecha  = now_local().strftime('%d/%m/%Y %H:%M')
    # Reintento: si dos workers calculan el mismo número, el UNIQUE rechaza al
    # segundo, que recalcula sobre lo ya insertado.
    for _ in range(5):
        numero = generar_numero(conn)
        try:
            conn.execute(
                'INSERT INTO solicitudes (numero, sucursal, creado_por, fecha_solicitud) VALUES (?,?,?,?)',
                (numero, sucursal, creado_por, fecha)
            )
            break
        except sqlite3.IntegrityError:
            continue
    else:
        conn.close()
        raise RuntimeError('No se pudo asignar un número de solicitud único')
    sol_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
    for it in items:
        conn.execute(
            'INSERT INTO items_solicitud (solicitud_id, sku, ean, descripcion, laboratorio, cantidad, drogueria, observacion) VALUES (?,?,?,?,?,?,?,?)',
            (sol_id, it['sku'], it.get('ean',''), it['descripcion'], it.get('laboratorio',''), it['cantidad'], it.get('drogueria',''), it.get('observacion') or None)
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

def get_todas_solicitudes(sucursal_filtro=None, lab_filtro=None, drogueria_filtro=None, q_filtro=None):
    conn = get_db()
    query = 'SELECT s.*, COUNT(i.id) as n_items FROM solicitudes s LEFT JOIN items_solicitud i ON i.solicitud_id=s.id AND i.cancelado=0'
    params = []
    wheres = []
    if sucursal_filtro:
        wheres.append('s.sucursal=?'); params.append(sucursal_filtro)
    if lab_filtro:
        wheres.append("EXISTS (SELECT 1 FROM items_solicitud li WHERE li.solicitud_id=s.id "
                      "AND li.cancelado=0 AND li.laboratorio LIKE ?)")
        params.append(f'%{lab_filtro}%')
    if drogueria_filtro:
        wheres.append("EXISTS (SELECT 1 FROM items_solicitud di WHERE di.solicitud_id=s.id "
                      "AND di.cancelado=0 AND di.drogueria_final=?)")
        params.append(drogueria_filtro)
    if q_filtro:
        like = f'%{q_filtro}%'
        wheres.append("EXISTS (SELECT 1 FROM items_solicitud qi WHERE qi.solicitud_id=s.id "
                      "AND qi.cancelado=0 AND (qi.descripcion LIKE ? OR qi.ean LIKE ? OR qi.sku LIKE ?))")
        params += [like, like, like]
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
        SELECT s.sucursal, i.drogueria AS drogueria,
               SUM(i.cantidad)        as cantidad,
               MIN(i.ordenado)        as ordenado,
               MAX(i.drogueria_final) as drogueria_final,
               MAX(i.observacion)     as observacion
        FROM items_solicitud i
        JOIN solicitudes s ON s.id = i.solicitud_id
        WHERE i.sku=? AND s.estado='pendiente' AND i.cancelado=0 AND i.comprado=0
        GROUP BY s.sucursal, i.drogueria
        ORDER BY s.sucursal
    ''', (sku,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def mover_item_sucursal(sku, sucursal, drogueria):
    """Cambia la droguería (tarjeta) de los ítems pendientes de un producto para UNA sucursal.
    Permite mover la línea de una sucursal a otra droguería sin tocar a las demás."""
    conn = get_db()
    conn.execute('''
        UPDATE items_solicitud SET drogueria=?
        WHERE sku=? AND cancelado=0 AND comprado=0
          AND solicitud_id IN (SELECT id FROM solicitudes WHERE sucursal=? AND estado='pendiente')
    ''', (drogueria, sku, sucursal))
    conn.commit()
    conn.close()

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
        UPDATE items_solicitud SET cancelado=1, sin_necesidad=0
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
        UPDATE items_solicitud SET cancelado=1, sin_necesidad=0
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
    conn.execute("UPDATE items_solicitud SET cancelado=0, sin_necesidad=0 WHERE id=?", (item_id,))
    # Reabrir el pedido si estaba cerrado (cancelado O comprado) y recalcular su estado real.
    # Antes solo contemplaba 'cancelado': un item restaurado en un pedido auto-cerrado como
    # 'comprado' quedaba pendiente pero el pedido seguia cerrado, y no aparecia en Generar orden.
    conn.execute("UPDATE solicitudes SET estado='pendiente', fecha_compra=NULL WHERE id=? AND estado IN ('cancelado','comprado')", (row['solicitud_id'],))
    _recalc_estado_solicitud(conn, row['solicitud_id'])
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

def cerrar_pedido_forzado(sol_id):
    """Cierra un pedido a la fuerza: los items que aun no estaban comprados quedan
    marcados como comprados ('Pedido realizado'), aunque no se hayan enviado todas las
    unidades pedidas. Recalcula el estado de la solicitud (pasa a 'comprado').
    Devuelve la cantidad de items afectados."""
    conn = get_db()
    fecha = now_local().strftime('%d/%m/%Y')
    cur = conn.execute(
        "UPDATE items_solicitud SET comprado=1, fecha_orden=COALESCE(fecha_orden, ?) "
        "WHERE solicitud_id=? AND cancelado=0 AND comprado=0",
        (fecha, sol_id))
    n = cur.rowcount
    _recalc_estado_solicitud(conn, sol_id)
    conn.commit()
    conn.close()
    return n


def marcar_sin_necesidad(sku, sucursal=None):
    """Saca un producto de la orden por 'sin necesidad' (queda cancelado con ese motivo).
    Con sucursal=None aplica a todas las sucursales pendientes; si se pasa, solo a esa."""
    conn = get_db()
    if sucursal:
        sols = [r['id'] for r in conn.execute(
            "SELECT id FROM solicitudes WHERE sucursal=? AND estado='pendiente'", (sucursal,)).fetchall()]
        conn.execute('''UPDATE items_solicitud SET cancelado=1, sin_necesidad=1
            WHERE sku=? AND solicitud_id IN (SELECT id FROM solicitudes WHERE sucursal=? AND estado='pendiente')''',
            (sku, sucursal))
    else:
        sols = [r['id'] for r in conn.execute('''SELECT DISTINCT s.id FROM solicitudes s
            JOIN items_solicitud i ON i.solicitud_id=s.id
            WHERE i.sku=? AND s.estado='pendiente' AND i.cancelado=0''', (sku,)).fetchall()]
        conn.execute('''UPDATE items_solicitud SET cancelado=1, sin_necesidad=1
            WHERE sku=? AND solicitud_id IN (SELECT id FROM solicitudes WHERE estado='pendiente')''', (sku,))
    for sid in sols:
        _recalc_estado_solicitud(conn, sid)
    conn.commit()
    conn.close()

def limpiar_sin_existencia_discontinuados(active_skus, active_eans):
    """Marca como inexistentes los items de 'Sin existencia' (droguería vacía, pendientes)
    cuyo producto YA NO está en el catálogo activo (ni por sku ni por EAN). Los que siguen
    activos se mantienen. Devuelve la cantidad de productos marcados."""
    a_sku = set(str(x) for x in (active_skus or []))
    a_ean = set(str(x).strip() for x in (active_eans or []) if str(x).strip())
    conn = get_db()
    rows = conn.execute(
        "SELECT DISTINCT i.sku AS sku, i.ean AS ean FROM items_solicitud i "
        "JOIN solicitudes s ON s.id=i.solicitud_id "
        "WHERE s.estado='pendiente' AND i.cancelado=0 AND i.comprado=0 AND COALESCE(i.drogueria,'')=''"
    ).fetchall()
    to_mark = []
    for r in rows:
        sku = str(r['sku']); ean = str(r['ean'] or '').strip()
        if sku in a_sku or (ean and ean in a_ean):
            continue  # sigue activo -> se queda
        to_mark.append(sku)
    afectadas = set()
    for sku in to_mark:
        for x in conn.execute("SELECT DISTINCT s.id AS id FROM solicitudes s "
                "JOIN items_solicitud i ON i.solicitud_id=s.id "
                "WHERE i.sku=? AND s.estado='pendiente' AND i.cancelado=0", (sku,)).fetchall():
            afectadas.add(x['id'])
        conn.execute("UPDATE items_solicitud SET cancelado=1, drogueria_final='INEXISTENTE' "
            "WHERE sku=? AND cancelado=0 AND solicitud_id IN (SELECT id FROM solicitudes WHERE estado='pendiente')", (sku,))
    for sid in afectadas:
        _recalc_estado_solicitud(conn, sid)
    conn.commit()
    conn.close()
    return len(to_mark)

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

def registrar_envio(sucursal, sku, drogueria, cantidad, usuario=None):
    """Registra (o actualiza) cuántas unidades se envían de un producto a una
    sucursal desde una droguería, con fecha y usuario para auditoría."""
    conn = get_db()
    try:
        cant = int(cantidad)
    except (TypeError, ValueError):
        cant = 0
    if cant > 0:
        fecha = now_local().strftime('%d/%m/%Y %H:%M')
        conn.execute('''INSERT INTO envios (sucursal, sku, drogueria, cantidad, fecha, usuario)
            VALUES (?,?,?,?,?,?)
            ON CONFLICT(sucursal, sku, drogueria) DO UPDATE SET
              cantidad=excluded.cantidad, fecha=excluded.fecha, usuario=excluded.usuario, exportado=0''',
            (sucursal, sku, drogueria, cant, fecha, usuario))
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

def get_rotacion_marcada():
    """Set de (sucursal, sku) que el admin marcó como ROTACIÓN en Generar orden
    (envío con droguería 'ROT'). Se usa para resaltar esas filas en el reporte."""
    conn = get_db()
    rows = conn.execute("SELECT sucursal, sku FROM envios WHERE drogueria='ROT' AND cantidad>0").fetchall()
    conn.close()
    return {(str(r['sucursal']), str(r['sku'])) for r in rows}


def marcar_envios_exportados(sucursal, drogueria, skus):
    """Marca como ya exportados los envíos incluidos en una descarga, para que una segunda
    descarga no los repita. Si luego se cambia la cantidad (registrar_envio), se resetea a 0."""
    skus = [x for x in (skus or []) if x]
    if not skus:
        return
    conn = get_db()
    marcadores = ','.join('?' * len(skus))
    conn.execute(
        f"UPDATE envios SET exportado=1 WHERE sucursal=? AND drogueria=? AND sku IN ({marcadores})",
        [sucursal, drogueria, *skus])
    conn.commit()
    conn.close()

def get_envios_sucursal_drogueria(sucursal, drogueria):
    """Unidades enviadas de cada producto a una sucursal desde una droguería (para export por sucursal).

    Solo incluye productos que siguen en un pedido PENDIENTE de esa sucursal, para que el archivo
    exportado coincida con lo que se ve en la orden y no arrastre envíos de pedidos ya cerrados.
    No borra ni modifica la tabla de envíos (queda intacta para la auditoría / Cumplimiento)."""
    conn = get_db()
    rows = conn.execute(
        """SELECT e.sku, e.cantidad FROM envios e
           WHERE e.sucursal=? AND e.drogueria=? AND e.cantidad>0
             AND (e.exportado IS NULL OR e.exportado = 0)
             AND EXISTS (
               SELECT 1 FROM items_solicitud i
               JOIN solicitudes s ON s.id = i.solicitud_id
               WHERE i.sku = e.sku AND s.sucursal = e.sucursal
                 AND s.estado = 'pendiente' AND i.cancelado = 0
             )""",
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

def get_cumplimiento(dias=None):
    """Métricas de servicio para el admin. dias=None -> histórico completo.
    Todo se calcula en Python: son cientos de filas, no vale SQL acrobático."""
    from datetime import datetime, timedelta

    def _fecha(s):
        try:
            return datetime.strptime((s or '').split(' ')[0], '%d/%m/%Y').date()
        except ValueError:
            return None

    hoy = now_local().date()
    corte = (hoy - timedelta(days=int(dias))) if dias else None

    conn = get_db()
    sols = [dict(r) for r in conn.execute('SELECT * FROM solicitudes')]
    items = [dict(r) for r in conn.execute('''
        SELECT i.*, s.sucursal AS suc, s.estado AS sol_estado, s.fecha_solicitud AS sol_fecha
        FROM items_solicitud i JOIN solicitudes s ON s.id = i.solicitud_id''')]
    conn.close()

    if corte:
        sols = [s for s in sols if (_fecha(s['fecha_solicitud']) or hoy) >= corte]
        items = [i for i in items if (_fecha(i['sol_fecha']) or hoy) >= corte]

    # ── Global ──
    compradas = [s for s in sols if s['estado'] == 'comprado']
    demoras = []
    for s in compradas:
        f_sol, f_com = _fecha(s['fecha_solicitud']), _fecha(s['fecha_compra'])
        if f_sol and f_com:
            demoras.append((f_com - f_sol).days)
    activas = [s for s in sols if s['estado'] != 'cancelado']
    glob = {
        'solicitudes': len(sols),
        'compradas': len(compradas),
        'pendientes': sum(1 for s in sols if s['estado'] == 'pendiente'),
        'canceladas': sum(1 for s in sols if s['estado'] == 'cancelado'),
        'pct_compradas': round(100 * len(compradas) / len(activas), 1) if activas else 0.0,
        'dias_promedio_compra': round(sum(demoras) / len(demoras), 1) if demoras else None,
    }

    # ── Por sucursal (unidades; excluye items/solicitudes cancelados) ──
    por_suc = {}
    for i in items:
        if i['cancelado'] or i['sol_estado'] == 'cancelado':
            continue
        d = por_suc.setdefault(i['suc'], {'pedido_u': 0, 'atendido_u': 0, 'pendiente_u': 0})
        cant = i['cantidad'] or 0
        d['pedido_u'] += cant
        if i['comprado'] or i['ordenado']:
            d['atendido_u'] += cant
        else:
            d['pendiente_u'] += cant
    por_sucursal = sorted(
        ({'sucursal': s, **v,
          'pct': round(100 * v['atendido_u'] / v['pedido_u'], 1) if v['pedido_u'] else 0.0}
         for s, v in por_suc.items()),
        key=lambda x: x['pct'])

    # ── Productos demorados: pendientes sin procesar, agrupados por sku ──
    dem = {}
    for i in items:
        if i['cancelado'] or i['comprado'] or i['ordenado'] or i['sol_estado'] != 'pendiente':
            continue
        f = _fecha(i['sol_fecha']) or hoy
        d = dem.setdefault(i['sku'], {'sku': i['sku'], 'descripcion': i['descripcion'],
                                      'cantidad': 0, 'sucursales': set(), 'desde': f})
        d['cantidad'] += i['cantidad'] or 0
        d['sucursales'].add(i['suc'])
        if f < d['desde']:
            d['desde'] = f
    demorados = sorted(
        ({'sku': d['sku'], 'descripcion': d['descripcion'], 'cantidad': d['cantidad'],
          'sucursales': sorted(d['sucursales']), 'dias': (hoy - d['desde']).days}
         for d in dem.values()),
        key=lambda x: -x['dias'])

    return {'global': glob, 'por_sucursal': por_sucursal, 'demorados': demorados}


def get_ranking(period='pendiente'):
    """Ranking de laboratorios y productos mas pedidos. period: 'pendiente' | 'mes' | 'todo'."""
    from datetime import datetime, timedelta
    conn = get_db()
    rows = conn.execute("""
        SELECT i.sku, i.ean, i.descripcion, i.laboratorio, i.cantidad, i.cancelado, s.estado, s.fecha_solicitud
        FROM items_solicitud i JOIN solicitudes s ON s.id = i.solicitud_id
    """).fetchall()
    conn.close()
    corte = (now_local() - timedelta(days=30)).date()
    labs, prods = {}, {}
    for r in rows:
        if r['cancelado']:
            continue
        if period == 'pendiente' and r['estado'] != 'pendiente':
            continue
        if period == 'mes':
            try:
                fs = datetime.strptime((r['fecha_solicitud'] or '').split(' ')[0], '%d/%m/%Y').date()
            except ValueError:
                continue
            if fs < corte:
                continue
        lab = r['laboratorio'] or '(sin laboratorio)'
        labs[lab] = labs.get(lab, 0) + (r['cantidad'] or 0)
        key = (r['sku'], r['ean'], r['descripcion'], lab)
        prods[key] = prods.get(key, 0) + (r['cantidad'] or 0)
    labs_r  = sorted(labs.items(), key=lambda x: -x[1])
    prods_r = sorted([(k[1], k[2], k[3], v) for k, v in prods.items()], key=lambda x: -x[3])
    return labs_r, prods_r

def carrito_set(sucursal, sku, ean, desc, lab, drog, cantidad, observacion=None):
    conn = get_db()
    try: c = int(cantidad)
    except (TypeError, ValueError): c = 0
    if c > 0:
        conn.execute("""INSERT INTO carrito (sucursal, sku, ean, descripcion, laboratorio, drogueria, cantidad, observacion)
            VALUES (?,?,?,?,?,?,?,?)
            ON CONFLICT(sucursal, sku) DO UPDATE SET cantidad=excluded.cantidad, ean=excluded.ean,
              descripcion=excluded.descripcion, laboratorio=excluded.laboratorio, drogueria=excluded.drogueria""",
            (sucursal, sku, ean, desc, lab, drog, c, observacion))
    else:
        conn.execute("DELETE FROM carrito WHERE sucursal=? AND sku=?", (sucursal, sku))
    conn.commit()
    conn.close()

def carrito_set_obs(sucursal, sku, obs):
    conn = get_db()
    conn.execute("UPDATE carrito SET observacion=? WHERE sucursal=? AND sku=?", (obs, sucursal, sku))
    conn.commit()
    conn.close()

def get_carrito(sucursal):
    conn = get_db()
    rows = conn.execute("SELECT * FROM carrito WHERE sucursal=? ORDER BY id", (sucursal,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def carrito_clear(sucursal):
    conn = get_db()
    conn.execute("DELETE FROM carrito WHERE sucursal=?", (sucursal,))
    conn.commit()
    conn.close()

def cancelar_solicitud(sol_id):
    conn = get_db()
    cur = conn.execute(
        "UPDATE solicitudes SET estado='cancelado' WHERE id=? AND estado='pendiente'", (sol_id,)
    )
    if cur.rowcount:
        # que los productos del detalle tambien queden como cancelados
        conn.execute('UPDATE items_solicitud SET cancelado=1 WHERE solicitud_id=? AND cancelado=0', (sol_id,))
    conn.commit()
    conn.close()


def set_fuente_estado(fuente, ok, filas, error):
    conn = get_db()
    ahora = now_local().strftime('%d/%m/%Y %H:%M')
    if ok:
        conn.execute('''INSERT INTO fuentes_estado (fuente, ultima_ok, filas, error, actualizado)
            VALUES (?,?,?,NULL,?)
            ON CONFLICT(fuente) DO UPDATE SET ultima_ok=excluded.ultima_ok,
                filas=excluded.filas, error=NULL, actualizado=excluded.actualizado''',
            (fuente, ahora, filas, ahora))
    else:
        conn.execute('''INSERT INTO fuentes_estado (fuente, filas, error, actualizado)
            VALUES (?,?,?,?)
            ON CONFLICT(fuente) DO UPDATE SET error=excluded.error,
                actualizado=excluded.actualizado''',
            (fuente, filas, error or 'error desconocido', ahora))
    conn.commit()
    conn.close()


def get_fuentes_estado():
    conn = get_db()
    rows = conn.execute('SELECT * FROM fuentes_estado ORDER BY fuente').fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_mapeo_cd():
    conn = get_db()
    rows = conn.execute('SELECT codigo_quantio, sku FROM mapeo_cd').fetchall()
    conn.close()
    return {r['codigo_quantio']: r['sku'] for r in rows}


def agregar_mapeos_cd(pares):
    conn = get_db()
    n = 0
    for codigo, sku in pares:
        codigo, sku = str(codigo).strip(), str(sku).strip()
        if codigo and sku:
            conn.execute('''INSERT INTO mapeo_cd (codigo_quantio, sku) VALUES (?,?)
                ON CONFLICT(codigo_quantio) DO UPDATE SET sku=excluded.sku''', (codigo, sku))
            n += 1
    conn.commit()
    conn.close()
    return n
