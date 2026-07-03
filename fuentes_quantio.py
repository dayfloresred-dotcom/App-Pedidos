"""Conector read-only al MySQL de Quantio (stock del CD).
QUERY_STOCK y CAMPOS se fijan tras la Fase 0 de exploración del schema
(docs/quantio_cd_schema.md). Mientras QUERY_STOCK sea None la fuente está
deshabilitada y el stock CD sale del archivo manual (fallback)."""
from config import CD_MYSQL, fuente_mysql_configurada

QUERY_STOCK = None  # ← lo fija la tarea de Fase 0 con el schema real
CAMPOS = {'codigo': 'codigo', 'ean': 'ean', 'troquel': 'troquel', 'cantidad': 'cantidad'}


def configurada():
    return fuente_mysql_configurada(CD_MYSQL) and QUERY_STOCK is not None


def _conn():
    import pymysql
    return pymysql.connect(
        host=CD_MYSQL['host'], port=CD_MYSQL['port'], user=CD_MYSQL['user'],
        password=CD_MYSQL['password'], database=CD_MYSQL['db'],
        connect_timeout=10, read_timeout=60,
        cursorclass=pymysql.cursors.DictCursor)


def cargar_stock_cd():
    """Devuelve filas normalizadas: [{'codigo','ean','troquel','cantidad'}]."""
    if QUERY_STOCK is None:
        raise RuntimeError('Fuente Quantio CD sin configurar (falta Fase 0)')
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(QUERY_STOCK)
            crudas = cur.fetchall()
    finally:
        conn.close()
    filas = []
    for r in crudas:
        filas.append({
            'codigo':   str(r.get(CAMPOS['codigo']) or '').strip(),
            'ean':      str(r.get(CAMPOS['ean']) or '').strip() if CAMPOS['ean'] else '',
            'troquel':  str(r.get(CAMPOS['troquel']) or '').strip() if CAMPOS['troquel'] else '',
            'cantidad': int(float(r.get(CAMPOS['cantidad']) or 0)),
        })
    return filas


def matchear_cd(filas_cd, productos, mapeo_manual):
    """Cascada: código==sku directo → EAN → troquel → mapeo manual.
    Devuelve ({sku: cantidad_total}, [filas sin match con cantidad > 0])."""
    por_ean, por_troquel = {}, {}
    for sku, p in productos.items():
        if p.get('ean'):
            por_ean.setdefault(p['ean'], sku)
        if p.get('troquel'):
            por_troquel.setdefault(p['troquel'], sku)

    stock, no_match = {}, []
    for f in filas_cd:
        if f['cantidad'] <= 0:
            continue
        sku = None
        if f['codigo'] and f['codigo'] in productos:
            sku = f['codigo']
        elif f['ean'] and f['ean'] in por_ean:
            sku = por_ean[f['ean']]
        elif f['troquel'] and f['troquel'] in por_troquel:
            sku = por_troquel[f['troquel']]
        elif f['codigo'] and f['codigo'] in mapeo_manual:
            sku = mapeo_manual[f['codigo']]
            if sku not in productos:
                sku = None
        if sku:
            stock[sku] = stock.get(sku, 0) + f['cantidad']
        else:
            no_match.append(f)
    return stock, no_match
