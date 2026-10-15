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
                    FUENTES_RUBROS, AJUSTE_STOCK_POSADAS1, fuente_mysql_configurada)

EXCLUIR = {'17', '33'}  # mismo criterio que data_loader

# Ocultos / duplicados: `medicamentos` arrastra el histórico completo y trae
# duplicados ocultos del mismo EAN (p. ej. laboratorio "DROGUERIA BARRACAS"),
# que se colaban porque `Activo='S'` no los filtra (tienen Activo='S' visible=0).
# El flag correcto es `visible` (tinyint 1/0, default 1; confirmado por Eze
# 2026-08-27). PERO visible=0 NO significa "no se vende": medido sobre el
# catálogo real de la app (tras el filtro por venta/stock), `visible=1` a secas
# sacaba 60 productos — 29 duplicados (bien) pero 31 sin gemelo, de los cuales 8
# son medicamentos que SÍ se venden (AMLODIPINA, BUSCAPINA DUO, PHARMATON,
# GENOPRAZOL, PERVINOX, ALERGICAL, NEUMOTEX, CARBOPLATINO). `visible` parece ser
# visibilidad de e-commerce, no de mostrador.
# Por eso el criterio es: incluir si está visible, O si (Activo='S' y NO tiene un
# gemelo visible con el mismo codebar). Así se van SOLO los duplicados ocultos y
# se conservan los medicamentos huérfanos. COALESCE(visible,1) por las 5 filas
# con visible NULL (una con ventas: CARQUEJA TROP), que por el default=1 quedan.
# El contraejemplo viejo (DOVE HIDRATACION INTENSA, SKU 3002602024/3002602032)
# hoy no tiene venta ni stock, así que queda afuera con cualquiera de los dos.
Q_PRODUCTOS = """
    SELECT m.CodPlex AS sku, m.Producto AS descripcion, m.Presentaci AS presentacion,
           l.Laborato AS laboratorio, r.Rubro AS rubro, m.Troquel AS troquel
    FROM medicamentos m
    LEFT JOIN laboratorios l ON l.CodLab = m.CodLab
    LEFT JOIN rubros r ON r.CodRubro = m.CodRubro
    WHERE (COALESCE(m.visible, 1) = 1
           OR (m.Activo = 'S' AND NOT EXISTS (
               SELECT 1 FROM medicamentos v
               WHERE v.codebar = m.codebar AND v.codebar <> ''
                 AND v.visible = 1 AND v.CodPlex <> m.CodPlex)))
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

# --- AJUSTE TEMPORAL: stock de Posadas I (sucursal 10) ----------------------
# El 15/09/2026 20:38 la base central registró una segunda "Confirmación de
# Stock" masiva de Posadas I (28.975 líneas) que repite el stock que ya había:
# la cantidad confirmada es igual al stock previo, así que la central muestra
# el doble que el Plex de la sucursal (ALPERTAN D: central 117, sucursal 47 =
# 117 − 70). Las demás sucursales tienen una sola confirmación (la carga
# inicial). Mismo ajuste que el portal (comercial-farmacias-red,
# _lib/ajuste-stock-posadas1.js, PRs #223/#224): se descuenta solo en las
# líneas seguras — confirmación == suma de movimientos previos y stock >= suma
# de todos los movimientos — así se apaga solo por producto si borran la línea
# o ajustan el stock. Entero con AJUSTE_STOCK_POSADAS1=0.
SUCURSAL_AJUSTE = 10

Q_CONF_DUPLICADA_POSADAS1 = """
    SELECT c.IDProducto AS sku, c.Cantidad AS conf,
           SUM(CASE WHEN x.IDMovimiento < c.IDMovimiento THEN x.Cantidad ELSE 0 END) AS previo,
           SUM(x.Cantidad) AS movimientos
    FROM stockmovimientos c
    JOIN stockmovimientos x ON x.Sucursal = c.Sucursal AND x.IDProducto = c.IDProducto
    WHERE c.Sucursal = 10
      AND c.Fecha = '2026-09-15' AND c.Hora BETWEEN '20:38:00' AND '20:39:00'
      AND c.Referencia LIKE 'Confirmaci%' AND c.Cantidad > 0
    GROUP BY c.IDMovimiento, c.IDProducto, c.Cantidad
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


_aviso_ajuste = None  # error del último ajuste de Posadas I, si falló


def aviso_ajuste():
    """Texto del error si el ajuste de Posadas I no se pudo aplicar en la
    última carga (el stock de esa sucursal quedó sin corregir)."""
    return _aviso_ajuste


def descontar_confirmacion_duplicada(rows_stock, rows_conf):
    """Pura: resta al stock de Posadas I las confirmaciones duplicadas seguras.
    Devuelve una lista nueva; no modifica la recibida."""
    stock_suc = {}
    for r in rows_stock:
        if str(r['sucursal']) == str(SUCURSAL_AJUSTE):
            sku = str(r['sku'])
            stock_suc[sku] = stock_suc.get(sku, 0) + float(r['cantidad'] or 0)

    dup = {}
    for r in rows_conf:
        sku = str(r['sku'])
        conf = float(r['conf'] or 0)
        if (sku in stock_suc and conf == float(r['previo'] or 0)
                and float(r['movimientos'] or 0) <= stock_suc[sku]):
            dup[sku] = dup.get(sku, 0) + conf
    if not dup:
        return rows_stock

    out = []
    for r in rows_stock:
        sku = str(r['sku'])
        if str(r['sucursal']) == str(SUCURSAL_AJUSTE) and sku in dup:
            r = {**r, 'cantidad': float(r['cantidad'] or 0) - dup.pop(sku)}
        out.append(r)
    return out


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
            rows_stock = _ajustar_posadas1(cur, rows_stock)
    finally:
        conn.close()
    return transformar(rows_prod, rows_eans, rows_ventas, rows_stock)


def _ajustar_posadas1(cur, rows_stock):
    """Aplica el ajuste de Posadas I. Si la consulta falla no tira abajo el
    refresco: el stock queda sin corregir y aviso_ajuste() lo informa (la
    tarjeta de Plex en admin queda 'Con aviso')."""
    global _aviso_ajuste
    _aviso_ajuste = None
    if not AJUSTE_STOCK_POSADAS1:
        return rows_stock
    try:
        cur.execute(Q_CONF_DUPLICADA_POSADAS1)
        return descontar_confirmacion_duplicada(rows_stock, cur.fetchall())
    except Exception as e:
        _aviso_ajuste = f'ajuste de stock de Posadas I sin aplicar ({type(e).__name__}: {e})'
        return rows_stock
