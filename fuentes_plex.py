"""Conector read-only al MySQL de Plex (ERP vivo).
DISCIPLINA: solo se consulta durante el refresco (cron diario + botón admin).
Las queries derivan del ETL probado de dashboard-bi; ante duda de schema
manda docs/erp_mysql_schema_legacy.md del comparador.

Deltas de nombres validados contra erp_mysql_schema_legacy.md y etl/etl.py
(dashboard-bi) respecto del plan original:
  - medicamentos: la PK/sku es CodPlex, no IDProducto.
  - laboratorios: la columna de nombre es Laborato, no Laboratorio.
  - productoscodebars: la columna del EAN es codebar (minuscula), no CodeBar.
  - Presentación/tamaño: la columna es `Presentaci` (varchar(50), nombre
    truncado en el schema), NO `Presentacion` ni `ProdPres` — esos dos son de
    la tabla `productos` de Quantio/CD, `medicamentos` no los tiene.
  - EAN "principal": el ETL usa medicamentos.codebar como principal y
    productoscodebars como alternativos/secundarios (ver sync_dim_productos_eans
    en etl.py). Q_EANS replica ese orden de prioridad: primero el codebar de
    medicamentos, luego productoscodebars como fallback.
  - Ventas en CAJAS: factlineas.CantDecimal está siempre en cajas; Cantidad
    viene en unidades sueltas cuando TipoCantidad='U' (venta fraccionada) y
    sumarla infla ×UnidadesPorCaja esos productos (verificado contra el
    informe manual de Ventas y Stock, 2026-07-06).
"""
from datetime import date, timedelta

from config import (PLEX, PLEX_FALLBACK, SUCURSALES, VENTAS_VENTANA_DIAS,
                    FUENTES_RUBROS, fuente_mysql_configurada)

EXCLUIR = {'17', '33'}  # mismo criterio que data_loader

# Vigencia / "ocultos": `medicamentos` arrastra el histórico completo. El campo
# que distingue lo vigente de lo oculto es `visible` (1=vigente, 0=oculto), NO
# `Activo`. Verificado 2026-08-21 comparando los listados de Plex "con ocultos"
# y "sin ocultos": el listado limpio son EXACTAMENTE los visible=1 (49.457, sin
# una sola excepción). En cambio `Activo='S'` estaba mal por partida doble:
#   - dejaba pasar 54.535 ocultos (Activo='S' pero visible=0), que aparecían en
#     la app (p. ej. duplicados con laboratorio "DROGUERIA BARRACAS"), y
#   - descartaba 99 productos vigentes (Activo='N' pero visible=1).
# Por eso se filtra por visible=1 y NO por Activo.
# NOTA: confirmar con Eze que en `medicamentos` la columna sea `visible` con
# valores 1/0 (en el export CSV figura como S/N). Si fuera texto, sería visible='S'.
Q_PRODUCTOS = """
    SELECT m.CodPlex AS sku, m.Producto AS descripcion, m.Presentaci AS presentacion,
           l.Laborato AS laboratorio, r.Rubro AS rubro, m.Troquel AS troquel
    FROM medicamentos m
    LEFT JOIN laboratorios l ON l.CodLab = m.CodLab
    LEFT JOIN rubros r ON r.CodRubro = m.CodRubro
    WHERE m.visible = 1
    {filtro_rubros}
"""

# EAN "principal": medicamentos.codebar tiene prioridad; productoscodebars
# son alternativos (mismo criterio que sync_dim_productos_eans en dashboard-bi).
# El UNION ALL trae primero los principales y transformar() se queda con el
# primero que ve por sku, preservando la prioridad.
Q_EANS = """
    SELECT m.CodPlex AS sku, m.codebar AS ean, 1 AS es_principal
    FROM medicamentos m
    WHERE m.codebar IS NOT NULL AND m.codebar != ''

    UNION ALL

    SELECT pc.IDProducto AS sku, pc.codebar AS ean, 0 AS es_principal
    FROM productoscodebars pc
"""

Q_VENTAS = """
    SELECT fl.IDProducto AS sku, fc.Sucursal AS sucursal,
           SUM(CASE WHEN fc.Tipo = 'NC' THEN -fl.CantDecimal ELSE fl.CantDecimal END) AS unidades
    FROM factlineas fl
    INNER JOIN factcabecera fc ON fc.IDComprobante = fl.IDComprobante
    WHERE fc.Emision >= %s
      AND fc.Tipo IN ('FA','TF','FV','TK','NC')
      AND fl.IDProducto > 0
    GROUP BY fl.IDProducto, fc.Sucursal
"""

Q_STOCK = """
    SELECT st.IDProducto AS sku, st.Sucursal AS sucursal, st.Cantidad AS cantidad
    FROM stock st
    WHERE st.IDProducto > 0 AND st.Cantidad IS NOT NULL
"""


def configurada():
    return fuente_mysql_configurada(PLEX)


def _connect(cfg):
    import pymysql
    return pymysql.connect(
        host=cfg['host'], port=cfg['port'], user=cfg['user'],
        password=cfg['password'], database=cfg['db'],
        connect_timeout=10, read_timeout=110,
        charset='utf8',  # el MySQL de Plex no conoce utf8mb4 (mismo charset que el ETL)
        cursorclass=pymysql.cursors.DictCursor)


_origen = 'replica'  # de la última conexión lograda: 'replica' | 'concentrador'


def _conn():
    """Conecta a la réplica (PLEX_*); si el connect falla y el concentrador
    (PLEX_FB_*, la base original, usuario read-only) está configurado, cae
    ahí. La réplica sigue siendo la conexión primaria: el concentrador se
    intenta solo ante fallo, en cada conexión."""
    global _origen
    try:
        conn = _connect(PLEX)
        _origen = 'replica'
        return conn
    except Exception:
        if not fuente_mysql_configurada(PLEX_FALLBACK):
            raise
        conn = _connect(PLEX_FALLBACK)
        _origen = 'concentrador'
        return conn


def origen_conexion():
    """'replica' o 'concentrador', según dónde se logró la última conexión."""
    return _origen


def _nombre_sucursal(sucursal):
    num = str(sucursal)
    if num in EXCLUIR:
        return None
    return SUCURSALES.get(num)


def _descripcion(producto, presentacion):
    """Nombre completo = `Producto` + `Presentaci`.

    `medicamentos.Producto` trae solo el nombre ('DOVE AC OLEO NUTRICION X');
    el tamaño vive aparte en `Presentaci` ('200ML'). Con la descripción a secas
    la app mostraba productos indistinguibles entre sí en todas las pantallas
    (todas leen esta descripción del catálogo). Si el nombre ya termina con la
    presentación no se repite."""
    nombre = str(producto or '').strip()
    pres   = str(presentacion or '').strip()
    if not pres or nombre.upper().endswith(pres.upper()):
        return nombre
    return f'{nombre} {pres}'.strip()


def transformar(rows_prod, rows_eans, rows_ventas, rows_stock):
    """Pura: filas SQL -> estructura del conector. Testeable sin conexión."""
    eans = {}
    for r in rows_eans:
        sku = str(r['sku'])
        ean = str(r['ean'] or '').strip()
        if ean and len(ean) >= 8 and sku not in eans:
            eans[sku] = ean

    productos = {}
    for r in rows_prod:
        sku = str(r['sku'])
        productos[sku] = {
            'descripcion': _descripcion(r['descripcion'], r.get('presentacion')),
            'laboratorio': str(r['laboratorio'] or '').strip(),
            'rubro':       str(r['rubro'] or '').strip(),
            'ean':         eans.get(sku, ''),
            'troquel':     str(r['troquel'] or '').strip(),
        }

    def _agrupar(rows, campo):
        out = {}
        for r in rows:
            sku = str(r['sku'])
            if sku not in productos:
                continue
            nombre = _nombre_sucursal(r['sucursal'])
            if not nombre:
                continue
            out.setdefault(sku, {})[nombre] = out.setdefault(sku, {}).get(nombre, 0) + int(r[campo] or 0)
        return out

    return {
        'productos': productos,
        'ventas':    _agrupar(rows_ventas, 'unidades'),
        'stock':     _agrupar(rows_stock, 'cantidad'),
    }


def cargar_ventas(dias):
    """Ventas por (sku, sucursal) de los ultimos `dias` dias.
    Devuelve {sku: {sucursal_nombre: unidades}}. Para el reporte de rotacion."""
    desde = (date.today() - timedelta(days=int(dias))).isoformat()
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(Q_VENTAS, (desde,))
            rows = cur.fetchall()
    finally:
        conn.close()
    out = {}
    for r in rows:
        nombre = _nombre_sucursal(r['sucursal'])
        if not nombre:
            continue
        sku = str(r['sku'])
        out.setdefault(sku, {})
        out[sku][nombre] = out[sku].get(nombre, 0) + int(r['unidades'] or 0)
    return out


def cargar():
    desde = (date.today() - timedelta(days=VENTAS_VENTANA_DIAS)).isoformat()
    conn = _conn()
    try:
        with conn.cursor() as cur:
            if FUENTES_RUBROS:
                filtro = 'AND r.Rubro IN (' + ','.join(['%s'] * len(FUENTES_RUBROS)) + ')'
                cur.execute(Q_PRODUCTOS.format(filtro_rubros=filtro), FUENTES_RUBROS)
            else:
                cur.execute(Q_PRODUCTOS.format(filtro_rubros=''))
            rows_prod = cur.fetchall()
            cur.execute(Q_EANS)
            rows_eans = cur.fetchall()
            cur.execute(Q_VENTAS, (desde,))
            rows_ventas = cur.fetchall()
            cur.execute(Q_STOCK)
            rows_stock = cur.fetchall()
    finally:
        conn.close()
    return transformar(rows_prod, rows_eans, rows_ventas, rows_stock)
