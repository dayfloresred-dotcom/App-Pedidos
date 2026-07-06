"""Diagnóstico: cómo reporta Plex las cantidades de los SKUs outliers
(cajas vs unidades) para replicar el criterio del informe manual."""
import os
import sys

sys.path.insert(0, os.environ.get('APP_DIR', '/app'))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date, timedelta

import fuentes_plex
from config import VENTAS_VENTANA_DIAS

SKUS_VENTAS = ['1016203403', '1073000040', '1021700078', '1015700016']
SKUS_STOCK = ['3003969296', '3003977364', '3003969310']
TODOS = SKUS_VENTAS + SKUS_STOCK

conn = fuentes_plex._conn()
try:
    with conn.cursor() as cur:
        marc = ','.join(['%s'] * len(TODOS))
        cur.execute(f"""SELECT CodPlex, Producto, Unidades, Fraccionable, UnidadesPadre
            FROM medicamentos WHERE CodPlex IN ({marc})""", TODOS)
        print('== medicamentos (Unidades = unidades por caja) ==')
        for r in cur.fetchall():
            print(f"  {r['CodPlex']} | Unidades={r['Unidades']} | Fracc={r['Fraccionable']} | "
                  f"UniPadre={r['UnidadesPadre']} | {str(r['Producto'])[:40]}")

        cur.execute(f"""SELECT IDProducto, Sucursal, Cantidad, Unidades, UnidadesProd
            FROM stock WHERE IDProducto IN ({marc}) AND (Cantidad != 0 OR Unidades != 0)
            ORDER BY IDProducto, Sucursal""", TODOS)
        print('\n== stock (Cantidad=cajas?, Unidades=sueltas?, UnidadesProd=u/caja?) ==')
        for r in cur.fetchall():
            print(f"  {r['IDProducto']} | suc {r['Sucursal']} | Cant={r['Cantidad']} | "
                  f"Unid={r['Unidades']} | UniProd={r['UnidadesProd']}")

        desde = (date.today() - timedelta(days=VENTAS_VENTANA_DIAS)).isoformat()
        marc_v = ','.join(['%s'] * len(SKUS_VENTAS))
        cur.execute(f"""SELECT fl.IDProducto, fc.Sucursal, fl.TipoCantidad,
                   SUM(CASE WHEN fc.Tipo = 'NC' THEN -fl.Cantidad ELSE fl.Cantidad END) AS cant,
                   SUM(CASE WHEN fc.Tipo = 'NC' THEN -fl.CantDecimal ELSE fl.CantDecimal END) AS cant_dec,
                   COUNT(*) AS lineas
            FROM factlineas fl
            INNER JOIN factcabecera fc ON fc.IDComprobante = fl.IDComprobante
            WHERE fc.Emision >= %s AND fc.Tipo IN ('FA','TF','FV','TK','NC')
              AND fl.IDProducto IN ({marc_v}) AND fc.Sucursal = 14
            GROUP BY fl.IDProducto, fc.Sucursal, fl.TipoCantidad""", [desde] + SKUS_VENTAS)
        print('\n== ventas NUEVO CENTRO (suc 14) por TipoCantidad ==')
        for r in cur.fetchall():
            print(f"  {r['IDProducto']} | tipo={r['TipoCantidad']!r} | Cantidad={r['cant']} | "
                  f"CantDecimal={r['cant_dec']} | lineas={r['lineas']}")

        cur.execute("""SELECT fl.TipoCantidad, COUNT(*) AS lineas
            FROM factlineas fl
            INNER JOIN factcabecera fc ON fc.IDComprobante = fl.IDComprobante
            WHERE fc.Emision >= %s AND fc.Tipo IN ('FA','TF','FV','TK','NC')
              AND fl.IDProducto > 0
            GROUP BY fl.TipoCantidad""", (desde,))
        print('\n== distribución global de TipoCantidad en la ventana ==')
        for r in cur.fetchall():
            print(f"  tipo={r['TipoCantidad']!r}: {r['lineas']} líneas")
finally:
    conn.close()
