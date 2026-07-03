"""Fase 0: exploración read-only del MySQL de Quantio (CD).
Uso (en el VPS): docker run --rm --env-file <(grep '^PEDIDOS_CD_' /opt/farmacias-red-comparador/.env | sed 's/^PEDIDOS_//') \
    -v /opt/App-Pedidos:/app -w /app python:3.12-slim \
    bash -c "pip install -q pymysql && python scripts/explorar_quantio.py" > /tmp/quantio_schema.md
Imprime markdown con tablas, columnas y samples de las tablas candidatas."""
import os
import re

import pymysql

PALABRAS_CLAVE = re.compile(r'stock|exist|producto|articulo|medicamento|deposito', re.I)

conn = pymysql.connect(
    host=os.environ['CD_HOST'], port=int(os.environ.get('CD_PORT') or 3306),
    user=os.environ['CD_USER'], password=os.environ['CD_PASSWORD'],
    database=os.environ['CD_DB'], connect_timeout=10, read_timeout=60,
    charset='utf8',
    cursorclass=pymysql.cursors.DictCursor)

print(f"# Schema Quantio CD — base `{os.environ['CD_DB']}`\n")
with conn.cursor() as cur:
    cur.execute("SHOW TABLES")
    tablas = [list(r.values())[0] for r in cur.fetchall()]
    print(f"Total de tablas: {len(tablas)}\n")
    print("## Todas las tablas\n\n" + ', '.join(f'`{t}`' for t in tablas) + "\n")
    print("## Tablas candidatas (stock/producto/existencia)\n")
    for t in tablas:
        if not PALABRAS_CLAVE.search(t):
            continue
        print(f"### `{t}`\n")
        cur.execute(f"SHOW COLUMNS FROM `{t}`")
        cols = cur.fetchall()
        print('| Columna | Tipo |')
        print('|---|---|')
        for c in cols:
            print(f"| {c['Field']} | {c['Type']} |")
        cur.execute(f"SELECT COUNT(*) AS n FROM `{t}`")
        print(f"\nFilas: {cur.fetchone()['n']}\n")
        cur.execute(f"SELECT * FROM `{t}` LIMIT 3")
        for i, fila in enumerate(cur.fetchall(), 1):
            resumen = {k: (str(v)[:40] if v is not None else None) for k, v in fila.items()}
            print(f"- sample {i}: `{resumen}`")
        print()
conn.close()
