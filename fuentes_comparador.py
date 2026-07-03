"""Conector read-only al Postgres del comparador (precios SUD/SUIZO).
En el VPS viaja por la red interna de Docker (host `postgres`).

Semántica de precio (validada contra los exportadores de listas del
comparador, 2026-07-03): `precios_snapshot.precio_con_descuento` es el
PRECIO FINAL — el sincronizador del comparador ya lo persiste con el factor
combinado aplicado (×0.88 si aplica el 12 %, ×1.21 si aplica IVA), que es
exactamente el "P. Final con IVA" / "Precio Final" de los XLSX que App-Pedidos
consumía a mano. `precio_con_iva` NO incluye el 12 % — no usar.

Matching: primero por sku (productos.sku_erp = CodPlex de Plex); fallback por
EAN (productos.ean_principal), igual que hacía el pipeline de archivos —
recupera los productos que el comparador matcheó solo por EAN."""
from datetime import datetime, timedelta, timezone

from config import COMPARADOR_DB_URL

STALE_HORAS = 48

Q_PRECIOS = """
    SELECT DISTINCT ON (ps.producto_id, ps.drogueria)
           p.sku_erp AS sku,
           p.ean_principal AS ean,
           ps.drogueria::text AS drogueria,
           ps.precio_con_descuento AS precio,
           p.cod_alfabeta,
           ps.consultado_at
    FROM precios_snapshot ps
    JOIN productos p ON p.id = ps.producto_id
    WHERE ps.drogueria::text IN ('DDS', 'SUIZO')
      AND ps.precio_con_descuento IS NOT NULL AND ps.precio_con_descuento > 0
    ORDER BY ps.producto_id, ps.drogueria, ps.consultado_at DESC
"""

_MAPA_DROG = {'DDS': 'SUD', 'SUIZO': 'SUIZO'}


def configurada():
    return bool(COMPARADOR_DB_URL)


def transformar(rows, ahora):
    """Pura: filas SQL -> precios por sku y por EAN (fallback), en la
    nomenclatura de App-Pedidos."""
    precios, precios_ean = {}, {}
    alfabeta, alfabeta_ean = {}, {}
    mas_reciente = None
    for r in rows:
        drog = _MAPA_DROG.get(r['drogueria'])
        if not drog:
            continue
        precio = float(r['precio'])
        sku = str(r['sku']) if r.get('sku') else ''
        ean = str(r['ean']).strip() if r.get('ean') else ''
        alfa = str(r['cod_alfabeta']) if r.get('cod_alfabeta') else ''
        if sku:
            precios.setdefault(sku, {'SUD': None, 'SUIZO': None})[drog] = precio
            if alfa:
                alfabeta[sku] = alfa
        if ean:
            precios_ean.setdefault(ean, {'SUD': None, 'SUIZO': None})[drog] = precio
            if alfa:
                alfabeta_ean[ean] = alfa
        ts = r['consultado_at']
        if ts is not None and (mas_reciente is None or ts > mas_reciente):
            mas_reciente = ts
    stale = mas_reciente is None or (ahora - mas_reciente) > timedelta(hours=STALE_HORAS)
    return {'precios': precios, 'precios_ean': precios_ean,
            'alfabeta': alfabeta, 'alfabeta_ean': alfabeta_ean,
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
    # consultado_at llega timezone-aware desde Postgres (timestamptz):
    # comparar contra un ahora igualmente aware.
    return transformar(rows, datetime.now(timezone.utc))
