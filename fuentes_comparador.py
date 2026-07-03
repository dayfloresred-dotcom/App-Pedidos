"""Conector read-only al Postgres del comparador (precios SUD/SUIZO).
En el VPS viaja por la red interna de Docker (host `postgres`)."""
from datetime import datetime, timedelta

from config import COMPARADOR_DB_URL

STALE_HORAS = 48

Q_PRECIOS = """
    SELECT DISTINCT ON (p.sku_erp, ps.drogueria)
           p.sku_erp AS sku,
           ps.drogueria::text AS drogueria,
           ps.precio_con_iva AS precio,
           p.cod_alfabeta,
           ps.consultado_at
    FROM precios_snapshot ps
    JOIN productos p ON p.id = ps.producto_id
    WHERE ps.drogueria::text IN ('DDS', 'SUIZO')
      AND ps.precio_con_iva IS NOT NULL AND ps.precio_con_iva > 0
      AND p.sku_erp IS NOT NULL
    ORDER BY p.sku_erp, ps.drogueria, ps.consultado_at DESC
"""

_MAPA_DROG = {'DDS': 'SUD', 'SUIZO': 'SUIZO'}


def configurada():
    return bool(COMPARADOR_DB_URL)


def transformar(rows, ahora):
    """Pura: filas SQL -> precios por sku con nomenclatura de App-Pedidos."""
    precios, alfabeta = {}, {}
    mas_reciente = None
    for r in rows:
        sku = str(r['sku'])
        drog = _MAPA_DROG.get(r['drogueria'])
        if not drog:
            continue
        precios.setdefault(sku, {'SUD': None, 'SUIZO': None})[drog] = float(r['precio'])
        if r.get('cod_alfabeta'):
            alfabeta[sku] = str(r['cod_alfabeta'])
        ts = r['consultado_at']
        if ts is not None and (mas_reciente is None or ts > mas_reciente):
            mas_reciente = ts
    stale = mas_reciente is None or (ahora - mas_reciente) > timedelta(hours=STALE_HORAS)
    return {'precios': precios, 'alfabeta': alfabeta,
            'mas_reciente': mas_reciente, 'stale': stale}


def cargar():
    import psycopg2
    import psycopg2.extras
    conn = psycopg2.connect(COMPARADOR_DB_URL, connect_timeout=10)
    try:
        conn.set_session(readonly=True)
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SET statement_timeout = '60s'")
            cur.execute(Q_PRECIOS)
            rows = cur.fetchall()
    finally:
        conn.close()
    return transformar(rows, datetime.now())
