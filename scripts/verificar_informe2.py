"""Verificación ronda 2: mismas comparaciones que verificar_informe.py pero
con queries CORREGIDAS por unidad de medida:
  - ventas: SUM(CantDecimal) — siempre en cajas (TipoCantidad U venía en unidades)
  - stock:  Cantidad + Unidades/UnidadesProd — cajas completas + sueltas convertidas
No toca el código de la app: valida que la corrección explica los deltas."""
import os
import sys

sys.path.insert(0, os.environ.get('APP_DIR', '/app'))
sys.path.insert(0, '/tmp')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date, timedelta

import fuentes_plex
from config import VENTAS_VENTANA_DIAS
from verificar_informe import parsear_informe, comparar_celdas

Q_VENTAS2 = """
    SELECT fl.IDProducto AS sku, fc.Sucursal AS sucursal,
           SUM(CASE WHEN fc.Tipo = 'NC' THEN -fl.CantDecimal ELSE fl.CantDecimal END) AS unidades
    FROM factlineas fl
    INNER JOIN factcabecera fc ON fc.IDComprobante = fl.IDComprobante
    WHERE fc.Emision >= %s
      AND fc.Tipo IN ('FA','TF','FV','TK','NC')
      AND fl.IDProducto > 0
    GROUP BY fl.IDProducto, fc.Sucursal
"""

Q_STOCK2 = """
    SELECT st.IDProducto AS sku, st.Sucursal AS sucursal,
           st.Cantidad + FLOOR(st.Unidades / GREATEST(COALESCE(st.UnidadesProd, 1), 1)) AS cantidad
    FROM stock st
    WHERE st.IDProducto > 0 AND st.Cantidad IS NOT NULL
"""


def main():
    ruta = sys.argv[1]
    archivo, sucs_archivo, _ = parsear_informe(ruta)
    print(f'ARCHIVO: {len(archivo)} productos')

    desde = (date.today() - timedelta(days=VENTAS_VENTANA_DIAS)).isoformat()
    conn = fuentes_plex._conn()
    try:
        with conn.cursor() as cur:
            cur.execute(fuentes_plex.Q_PRODUCTOS.format(filtro_rubros=''))
            rows_prod = cur.fetchall()
            cur.execute(Q_VENTAS2, (desde,))
            rows_ventas = cur.fetchall()
            cur.execute(Q_STOCK2)
            rows_stock = cur.fetchall()
    finally:
        conn.close()
    plex = fuentes_plex.transformar(rows_prod, [], rows_ventas, rows_stock)
    print(f'PLEX corregido: {len(plex["productos"])} productos | '
          f'{len(plex["ventas"])} con ventas | {len(plex["stock"])} con stock')

    en_plex = [sku for sku in archivo if sku in plex['productos']]
    comparar_celdas('ventas', archivo, plex['ventas'], sucs_archivo, en_plex)
    comparar_celdas('stock', archivo, plex['stock'], sucs_archivo, en_plex)


if __name__ == '__main__':
    main()
