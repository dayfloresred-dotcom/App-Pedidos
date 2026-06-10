import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, 'pedidos.db')

SECRET_KEY = 'farmacias-red-2026-secret'

# Mail
MAIL_SERVER   = 'smtp.gmail.com'
MAIL_PORT     = 587
MAIL_USE_TLS  = True
MAIL_USERNAME = 'dayflores.red@gmail.com'
MAIL_PASSWORD = 'koft updi dvzh rchz'
MAIL_ADMIN    = 'jenarraigada.red@gmail.com'

# Data directory: usa Necesidad Sucursales si existe (local), si no usa data/ (Railway/cloud)
_NEC_DIR = os.path.join(os.path.dirname(BASE_DIR), 'Necesidad Sucursales')
if os.path.isdir(_NEC_DIR):
    DATA_DIR          = _NEC_DIR
    PRESUPUESTO_CSV   = os.path.join(DATA_DIR, 'Presupuesto 08-06-26.csv')
    LISTADO_STOCK_CSV = os.path.join(DATA_DIR, 'Listado de Stock 6-4.csv')
    STOCK_CD_CSV      = os.path.join(DATA_DIR, 'Stock CD.csv')
    PRECIOS_SUD_TXT   = os.path.join(DATA_DIR, 'precios Sud.txt')
    PRECIOS_SUIZO_PERFU = os.path.join(DATA_DIR, 'precios perfu Suizo.xls')
    PRECIOS_SUIZO_INS   = os.path.join(DATA_DIR, 'precios insumos Suizo.xls')
else:
    DATA_DIR          = os.path.join(BASE_DIR, 'data')
    os.makedirs(DATA_DIR, exist_ok=True)
    PRESUPUESTO_CSV   = os.path.join(DATA_DIR, 'presupuesto.csv')
    LISTADO_STOCK_CSV = os.path.join(DATA_DIR, 'listado_stock.csv')
    STOCK_CD_CSV      = os.path.join(DATA_DIR, 'stock_cd.csv')
    PRECIOS_SUD_TXT   = os.path.join(DATA_DIR, 'precios_sud.txt')
    PRECIOS_SUIZO_PERFU = os.path.join(DATA_DIR, 'precios_suizo_perfu.xls')
    PRECIOS_SUIZO_INS   = os.path.join(DATA_DIR, 'precios_suizo_ins.xls')

# Sucursales: number -> name
SUCURSALES = {
    '2':'CERRO','6':'RECTA','9':'POSADAS 2','10':'POSADAS 1',
    '11':'RESISTENCIA','13':'URBANA','14':'NUEVO CENTRO','15':'URCA',
    '19':'ADMINISTRACION','20':'MARTINOLLI','21':'COLON','22':'RED MARKET',
    '23':'OHIGGINS','24':'REAL','25':'LIBERTAD','26':'PASEO RIVERA',
    '27':'CBA SHOPPING','28':'VILLA ALLENDE','29':'ITAEMBE GUAZU',
    '30':'SABATTINI','31':'LUGONES','32':'ARMA',
}
SUCURSAL_NAMES = list(SUCURSALES.values())

ADMIN_USER = 'admin'
