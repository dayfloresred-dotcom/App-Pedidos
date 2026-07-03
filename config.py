import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# En contenedor (VPS) el estado persistente vive en un volumen: setear
# PEDIDOS_DB_PATH y PEDIDOS_DATA_DIR. Sin esas variables se comporta igual
# que siempre (PythonAnywhere / local).
DB_PATH = os.environ.get('PEDIDOS_DB_PATH') or os.path.join(BASE_DIR, 'pedidos.db')

# Secret de sesiones: SIEMPRE setear SECRET_KEY en produccion. Sin la
# variable se genera una clave aleatoria al arrancar (las sesiones se
# invalidan en cada reinicio — aceptable solo en desarrollo).
SECRET_KEY = os.environ.get('SECRET_KEY') or __import__('secrets').token_hex(32)

# Mail: sin MAIL_USERNAME/MAIL_PASSWORD las notificaciones se omiten
# (mail_service ya contempla ese caso). Usar contraseña de aplicacion de Gmail.
MAIL_SERVER   = 'smtp.gmail.com'
MAIL_PORT     = 465
MAIL_USE_TLS  = True
MAIL_USERNAME = os.environ.get('MAIL_USERNAME', '')
MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', '')
MAIL_ADMIN    = os.environ.get('MAIL_ADMIN') or 'jenarraigada.red@gmail.com'

# Data directory, por prioridad:
#   1. PEDIDOS_DATA_DIR (contenedor, volumen persistente)
#   2. Necesidad Sucursales/ si existe (desarrollo local)
#   3. data/ junto al codigo (PythonAnywhere/cloud)
_ENV_DATA_DIR = os.environ.get('PEDIDOS_DATA_DIR', '')
_NEC_DIR = os.path.join(os.path.dirname(BASE_DIR), 'Necesidad Sucursales')
if not _ENV_DATA_DIR and os.path.isdir(_NEC_DIR):
    DATA_DIR          = _NEC_DIR
    PRESUPUESTO_CSV   = os.path.join(DATA_DIR, 'Presupuesto 08-06-26.csv')
    LISTADO_STOCK_CSV = os.path.join(DATA_DIR, 'Listado de Stock 6-4.csv')
    STOCK_CD_CSV      = os.path.join(DATA_DIR, 'Stock CD.csv')
    PRECIOS_SUD_TXT   = os.path.join(DATA_DIR, 'precios Sud.txt')
    PRECIOS_SUIZO_PERFU = os.path.join(DATA_DIR, 'precios perfu Suizo.xls')
    PRECIOS_SUIZO_INS   = os.path.join(DATA_DIR, 'precios insumos Suizo.xls')
    PRECIOS_DDS_XLSX       = os.path.join(DATA_DIR, 'precios DDS.xlsx')
    PRECIOS_SUIZO_CMP_XLSX = os.path.join(DATA_DIR, 'precios Suizo cmp.xlsx')
else:
    DATA_DIR          = _ENV_DATA_DIR or os.path.join(BASE_DIR, 'data')
    os.makedirs(DATA_DIR, exist_ok=True)
    PRESUPUESTO_CSV   = os.path.join(DATA_DIR, 'presupuesto.csv')
    LISTADO_STOCK_CSV = os.path.join(DATA_DIR, 'listado_stock.csv')
    STOCK_CD_CSV      = os.path.join(DATA_DIR, 'stock_cd.csv')
    PRECIOS_SUD_TXT   = os.path.join(DATA_DIR, 'precios_sud.txt')
    PRECIOS_SUIZO_PERFU = os.path.join(DATA_DIR, 'precios_suizo_perfu.xls')
    PRECIOS_SUIZO_INS   = os.path.join(DATA_DIR, 'precios_suizo_ins.xls')
    PRECIOS_DDS_XLSX       = os.path.join(DATA_DIR, 'precios_dds.xlsx')
    PRECIOS_SUIZO_CMP_XLSX = os.path.join(DATA_DIR, 'precios_suizo_cmp.xlsx')

# Sucursales: number -> name
SUCURSALES = {
    '2':'CERRO','6':'RECTA','9':'POSADAS 2','10':'POSADAS 1',
    '11':'RESISTENCIA','13':'URBANA','14':'NUEVO CENTRO','15':'URCA',
    '19':'ADMINISTRACION','20':'MARTINOLLI','21':'COLON','22':'RED MARKET',
    '23':'OHIGGINS','24':'REAL','25':'LIBERTAD','26':'PASEO RIVERA',
    '27':'CBA SHOPPING','28':'VILLA ALLENDE','29':'ITAEMBE GUAZU',
    '30':'SABATTINI','31':'LUGONES','32':'ARMADA',
}
SUCURSAL_NAMES = list(SUCURSALES.values())

ADMIN_USER = 'admin'

from datetime import datetime as _datetime, timezone as _timezone, timedelta as _timedelta

def now_local():
    """Hora local de Argentina (UTC-3, sin horario de verano)."""
    return _datetime.now(_timezone.utc).astimezone(_timezone(_timedelta(hours=-3)))

# ── Fuentes automáticas (todas read-only; ver spec 2026-07-03) ─────────────
def _mysql_cfg(prefijo):
    return {
        'host':     os.environ.get(f'{prefijo}_HOST', ''),
        'port':     int(os.environ.get(f'{prefijo}_PORT') or 3306),
        'user':     os.environ.get(f'{prefijo}_USER', ''),
        'password': os.environ.get(f'{prefijo}_PASSWORD', ''),
        'db':       os.environ.get(f'{prefijo}_DB', ''),
    }

PLEX     = _mysql_cfg('PLEX')
CD_MYSQL = _mysql_cfg('CD')

def fuente_mysql_configurada(cfg):
    return bool(cfg['host'] and cfg['user'] and cfg['password'] and cfg['db'])

COMPARADOR_DB_URL   = os.environ.get('COMPARADOR_DB_URL', '')
VENTAS_VENTANA_DIAS = int(os.environ.get('VENTAS_VENTANA_DIAS') or 60)
FUENTES_RUBROS      = [s.strip() for s in
                       (os.environ.get('FUENTES_RUBROS') or 'Perfumería,Accesorios').split(',') if s.strip()]
FUENTES_CRON_TOKEN  = os.environ.get('FUENTES_CRON_TOKEN', '')
