# Fuentes automáticas de datos — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reemplazar la carga manual de archivos por tres fuentes automáticas (MySQL Plex directo, Postgres del comparador, MySQL Quantio del CD) manteniendo el pipeline de archivos como fallback, según el spec `docs/superpowers/specs/2026-07-03-fuentes-automaticas-design.md`.

**Architecture:** Conectores read-only en módulos planos (`fuentes_plex.py`, `fuentes_comparador.py`, `fuentes_quantio.py`) con transformaciones puras testeables; orquestador `fuentes.py` con memoria last-good por fuente que ensambla la MISMA estructura de catálogo que `load_productos()` y escribe el mismo pickle. Endpoint único de refresco (botón admin + cron con token). La lógica de decisión de droguería se extrae a una función compartida.

**Tech Stack:** Flask 3, SQLite, pymysql (Plex y Quantio), psycopg2-binary (comparador), pytest.

## Global Constraints

- Rama `ui-redesign`. Commits en español + sufijo `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`. `git add` solo de archivos de la tarea.
- **Nada de credenciales en el repo** — todo por env. **Ninguna query nueva inventada contra Plex**: las queries salen del ETL probado de dashboard-bi, con nombres de columna validados contra `C:/Users/e.pernochi/Proyectos-Claude/farmacias-red-comparador/docs/erp_mysql_schema_legacy.md`.
- Los consumidores del catálogo NO cambian: `load_productos()` sigue siendo la puerta única; `construir_catalogo()` produce dicts con exactamente los campos: `sku, ean, descripcion, laboratorio, rubro, stock_cd, drogueria, mejor_precio, drog_ext, troquel, troquel_pres, necesidad, stock_real, ventas`.
- El pipeline de archivos manuales queda intacto (fallback).
- Conexiones a fuentes SOLO durante el refresco, nunca en requests de usuario. Timeouts en toda conexión.
- Las tareas marcadas **[VPS]** las ejecuta el controlador por SSH con participación del usuario — NO son para subagentes.
- `$PY` = `C:/Users/e.pernochi/AppData/Local/Temp/claude/C--Users-e-pernochi-Proyectos-Claude-App-pedidos/6678761c-1269-44c8-b258-9a9874cdb57b/scratchpad/venv-pedidos/Scripts/python.exe`. Working dir: `C:/Users/e.pernochi/Proyectos-Claude/App-pedidos`.

---

### Task 1: `decidir_drogueria()` compartida (refactor TDD en data_loader)

**Files:**
- Modify: `data_loader.py` (bloque de decisión en `load_productos`, líneas ~292-310)
- Test: `tests/test_decidir_drogueria.py`

**Interfaces:**
- Produces: `decidir_drogueria(stock_cd: int, p_sud: float|None, p_suizo: float|None) -> tuple` que devuelve `(drogueria: str, mejor_precio: float|None, drog_ext: str, precio_ext: float|None)`. La consumen `load_productos()` (esta tarea) y `construir_catalogo()` (Task 7).

- [ ] **Step 1: Test que falla** — crear `tests/test_decidir_drogueria.py`:

```python
from data_loader import decidir_drogueria


def test_con_stock_cd_va_a_drogueria_red():
    d, mejor, ext, p_ext = decidir_drogueria(5, 100.0, 200.0)
    assert d == 'DROGUERIA RED'
    assert mejor is None
    assert ext == 'SUD' and p_ext == 100.0


def test_sin_cd_elige_mas_barata():
    assert decidir_drogueria(0, 100.0, 90.0) == ('SUIZO', 90.0, 'SUIZO', 90.0)
    assert decidir_drogueria(0, 80.0, 90.0) == ('SUD', 80.0, 'SUD', 80.0)


def test_empate_gana_sud():
    assert decidir_drogueria(0, 100.0, 100.0)[0] == 'SUD'


def test_solo_una_drogueria():
    assert decidir_drogueria(0, None, 50.0) == ('SUIZO', 50.0, 'SUIZO', 50.0)
    assert decidir_drogueria(0, 50.0, None) == ('SUD', 50.0, 'SUD', 50.0)


def test_sin_precios_queda_sin_drogueria():
    assert decidir_drogueria(0, None, None) == ('', None, '', None)
```

- [ ] **Step 2: Correr y ver fallar** — Run: `$PY -m pytest tests/test_decidir_drogueria.py -v` — Expected: FAIL (ImportError).

- [ ] **Step 3: Implementar** — en `data_loader.py`, agregar arriba de `load_productos()`:

```python
def decidir_drogueria(stock_cd, p_sud, p_suizo):
    """Regla única de asignación de droguería (usada por archivos y fuentes).
    Devuelve (drogueria, mejor_precio, drog_ext, precio_ext)."""
    if p_sud and p_suizo:
        drog_ext = 'SUD' if p_sud <= p_suizo else 'SUIZO'
        precio_ext = min(p_sud, p_suizo)
    elif p_sud:
        drog_ext, precio_ext = 'SUD', p_sud
    elif p_suizo:
        drog_ext, precio_ext = 'SUIZO', p_suizo
    else:
        drog_ext, precio_ext = '', None
    if stock_cd > 0:
        return 'DROGUERIA RED', None, drog_ext, precio_ext
    return drog_ext, precio_ext, drog_ext, precio_ext
```

y reemplazar en `load_productos()` el bloque desde `# Always compute external droguería` hasta `mejor_precio = precio_ext` (inclusive el if/else de `tiene_cd`) por:

```python
                drogueria, mejor_precio, drog_ext, precio_ext = decidir_drogueria(
                    cant_cd, sud_p.get(ean), suizo_p.get(ean))
```

(La variable `tiene_cd` desaparece; `drog_ext` ya queda asignada por la función.)

- [ ] **Step 4: Verificar** — Run: `$PY -m pytest tests/ -v` — Expected: todos PASS (los 12 existentes + 5 nuevos).

- [ ] **Step 5: Commit**

```bash
git add data_loader.py tests/test_decidir_drogueria.py
git commit -m "Refactor: decidir_drogueria() compartida entre pipeline de archivos y fuentes"
```

---

### Task 2: Tablas y helpers de estado/mapeo en database.py (TDD)

**Files:**
- Modify: `database.py` (init_db + helpers al final)
- Test: `tests/test_fuentes_db.py`

**Interfaces:**
- Produces: `set_fuente_estado(fuente, ok: bool, filas: int, error: str|None)`, `get_fuentes_estado() -> list[dict]` (keys: fuente, ultima_ok, filas, error, actualizado), `get_mapeo_cd() -> dict[str, str]` (codigo_quantio→sku), `agregar_mapeos_cd(pares: list[tuple[str, str]]) -> int`. Consumidas por Tasks 6, 7, 8.

- [ ] **Step 1: Test que falla** — crear `tests/test_fuentes_db.py`:

```python
import database


def test_estado_fuente_upsert_y_lectura():
    database.init_db()
    database.set_fuente_estado('plex', True, 21000, None)
    database.set_fuente_estado('plex', False, 0, 'timeout')
    estados = {e['fuente']: e for e in database.get_fuentes_estado()}
    assert estados['plex']['error'] == 'timeout'
    assert estados['plex']['ultima_ok'] is not None  # la ultima_ok NO se pisa al fallar


def test_mapeo_cd():
    database.init_db()
    n = database.agregar_mapeos_cd([('Q123', '555'), ('Q124', '556'), ('Q123', '999')])
    assert n == 3  # el tercero pisa al primero (upsert)
    m = database.get_mapeo_cd()
    assert m['Q123'] == '999' and m['Q124'] == '556'
```

- [ ] **Step 2: Ver fallar** — Run: `$PY -m pytest tests/test_fuentes_db.py -v` — Expected: FAIL (AttributeError).

- [ ] **Step 3: Implementar** — en `init_db()` antes del bloque de índices:

```python
    conn.execute('''
        CREATE TABLE IF NOT EXISTS fuentes_estado (
            fuente      TEXT PRIMARY KEY,
            ultima_ok   TEXT,
            filas       INTEGER NOT NULL DEFAULT 0,
            error       TEXT,
            actualizado TEXT
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS mapeo_cd (
            codigo_quantio TEXT PRIMARY KEY,
            sku            TEXT NOT NULL
        )
    ''')
```

y al final de `database.py`:

```python
def set_fuente_estado(fuente, ok, filas, error):
    conn = get_db()
    ahora = now_local().strftime('%d/%m/%Y %H:%M')
    if ok:
        conn.execute('''INSERT INTO fuentes_estado (fuente, ultima_ok, filas, error, actualizado)
            VALUES (?,?,?,NULL,?)
            ON CONFLICT(fuente) DO UPDATE SET ultima_ok=excluded.ultima_ok,
                filas=excluded.filas, error=NULL, actualizado=excluded.actualizado''',
            (fuente, ahora, filas, ahora))
    else:
        conn.execute('''INSERT INTO fuentes_estado (fuente, filas, error, actualizado)
            VALUES (?,?,?,?)
            ON CONFLICT(fuente) DO UPDATE SET error=excluded.error,
                actualizado=excluded.actualizado''',
            (fuente, filas, error or 'error desconocido', ahora))
    conn.commit()
    conn.close()


def get_fuentes_estado():
    conn = get_db()
    rows = conn.execute('SELECT * FROM fuentes_estado ORDER BY fuente').fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_mapeo_cd():
    conn = get_db()
    rows = conn.execute('SELECT codigo_quantio, sku FROM mapeo_cd').fetchall()
    conn.close()
    return {r['codigo_quantio']: r['sku'] for r in rows}


def agregar_mapeos_cd(pares):
    conn = get_db()
    n = 0
    for codigo, sku in pares:
        codigo, sku = str(codigo).strip(), str(sku).strip()
        if codigo and sku:
            conn.execute('''INSERT INTO mapeo_cd (codigo_quantio, sku) VALUES (?,?)
                ON CONFLICT(codigo_quantio) DO UPDATE SET sku=excluded.sku''', (codigo, sku))
            n += 1
    conn.commit()
    conn.close()
    return n
```

- [ ] **Step 4: Verificar** — Run: `$PY -m pytest tests/ -v` — Expected: todos PASS.

- [ ] **Step 5: Commit**

```bash
git add database.py tests/test_fuentes_db.py
git commit -m "Fuentes: tablas fuentes_estado y mapeo_cd con helpers de upsert"
```

---

### Task 3: Dependencias y configuración de fuentes

**Files:**
- Modify: `requirements.txt`, `config.py`
- Test: `tests/test_config_fuentes.py`

**Interfaces:**
- Produces (en config.py): dicts `PLEX` y `CD_MYSQL` con keys `host, port, user, password, db`; `COMPARADOR_DB_URL: str`; `VENTAS_VENTANA_DIAS: int` (default 60); `FUENTES_RUBROS: list[str]` (default `['Perfumería', 'Accesorios']`); `FUENTES_CRON_TOKEN: str`; `fuente_mysql_configurada(cfg) -> bool`. Consumidas por Tasks 4-8.

- [ ] **Step 1: requirements.txt** — agregar al final:

```
pymysql==1.1.1
psycopg2-binary==2.9.9
```

Instalar en el venv: `$PY -m pip install -q pymysql==1.1.1 psycopg2-binary==2.9.9`

- [ ] **Step 2: Test que falla** — crear `tests/test_config_fuentes.py`:

```python
import importlib
import os


def test_config_fuentes_defaults_y_env(monkeypatch):
    monkeypatch.setenv('PLEX_HOST', 'h1')
    monkeypatch.setenv('PLEX_PORT', '6613')
    monkeypatch.setenv('VENTAS_VENTANA_DIAS', '45')
    import config
    importlib.reload(config)
    assert config.PLEX['host'] == 'h1' and config.PLEX['port'] == 6613
    assert config.VENTAS_VENTANA_DIAS == 45
    assert config.FUENTES_RUBROS == ['Perfumería', 'Accesorios']
    assert config.fuente_mysql_configurada(config.PLEX) is False  # falta user/pass/db
    monkeypatch.setenv('PLEX_USER', 'u')
    monkeypatch.setenv('PLEX_PASSWORD', 'p')
    monkeypatch.setenv('PLEX_DB', 'onze_center')
    importlib.reload(config)
    assert config.fuente_mysql_configurada(config.PLEX) is True
    importlib.reload(config)  # dejar config coherente para el resto de la suite
```

- [ ] **Step 3: Ver fallar** — Run: `$PY -m pytest tests/test_config_fuentes.py -v` — Expected: FAIL (AttributeError PLEX).

- [ ] **Step 4: Implementar** — al final de `config.py`:

```python
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
```

- [ ] **Step 5: Verificar** — Run: `$PY -m pytest tests/ -v` — Expected: todos PASS.

- [ ] **Step 6: Commit**

```bash
git add requirements.txt config.py tests/test_config_fuentes.py
git commit -m "Fuentes: dependencias mysql/postgres y configuracion por variables de entorno"
```

---

### Task 4: Conector Plex (`fuentes_plex.py`)

**Files:**
- Create: `fuentes_plex.py`
- Test: `tests/test_fuentes_plex.py`
- Reference (leer antes de tocar las queries): `C:/Users/e.pernochi/Proyectos-Claude/farmacias-red-comparador/docs/erp_mysql_schema_legacy.md` y `C:/Users/e.pernochi/Proyectos-Claude/dashboard-bi/etl/etl.py`

**Interfaces:**
- Consumes: `config.PLEX`, `config.SUCURSALES`, `config.VENTAS_VENTANA_DIAS`, `config.FUENTES_RUBROS`, `config.fuente_mysql_configurada`; `EXCLUIR` de data_loader.
- Produces: `cargar() -> dict` con estructura `{'productos': {sku: {'descripcion','laboratorio','rubro','ean','troquel'}}, 'ventas': {sku: {nombre_sucursal: int}}, 'stock': {sku: {nombre_sucursal: int}}}` y `transformar(rows_prod, rows_eans, rows_ventas, rows_stock) -> dict` (pura, misma salida). Consumidas por Task 7.

- [ ] **Step 1: Validar nombres de columnas contra el doc legacy.** Leer `erp_mysql_schema_legacy.md` (repo comparador, local) y `etl/etl.py` de dashboard-bi (funciones que cargan dim_productos, fact_ventas, fact_stock_diario) y anotar en el reporte los nombres EXACTOS de: tabla/columnas de productos (medicamentos: id, nombre, troquel, CodLab, CodRubro), laboratorios, rubros, productoscodebars (columna del EAN y criterio de "principal"), factlineas/factcabecera (IDProducto, Cantidad, IDComprobante, Sucursal, Tipo, Emision) y stock (IDProducto, Sucursal, Cantidad). **Si algún nombre difiere de las queries del Step 4, ajustar las queries — el doc y el ETL mandan, no este plan.**

- [ ] **Step 2: Test que falla (transformación pura)** — crear `tests/test_fuentes_plex.py`:

```python
from fuentes_plex import transformar


def test_transformar_arma_estructura():
    rows_prod = [
        {'sku': 555, 'descripcion': 'SHAMPOO X', 'laboratorio': 'LAB A', 'rubro': 'Perfumería', 'troquel': '1234567'},
        {'sku': 556, 'descripcion': 'CREMA Y', 'laboratorio': None, 'rubro': 'Accesorios', 'troquel': None},
    ]
    rows_eans = [{'sku': 555, 'ean': '7790000000001'}, {'sku': 999, 'ean': '779'}]
    rows_ventas = [
        {'sku': 555, 'sucursal': 2, 'unidades': 10},   # suc 2 = CERRO
        {'sku': 555, 'sucursal': 17, 'unidades': 99},  # excluida
        {'sku': 555, 'sucursal': 4040, 'unidades': 5}, # desconocida: se ignora
        {'sku': 777, 'sucursal': 2, 'unidades': 3},    # sku fuera de rubro: se ignora
    ]
    rows_stock = [{'sku': 556, 'sucursal': 6, 'cantidad': 4}]  # suc 6 = RECTA
    r = transformar(rows_prod, rows_eans, rows_ventas, rows_stock)
    assert r['productos']['555']['ean'] == '7790000000001'
    assert r['productos']['556']['ean'] == ''
    assert r['productos']['556']['laboratorio'] == ''
    assert r['ventas']['555'] == {'CERRO': 10}
    assert r['stock']['556'] == {'RECTA': 4}
    assert '777' not in r['ventas']


def test_ventas_negativas_no_rompen():
    rows_prod = [{'sku': 1, 'descripcion': 'P', 'laboratorio': 'L', 'rubro': 'Perfumería', 'troquel': None}]
    r = transformar(rows_prod, [], [{'sku': 1, 'sucursal': 2, 'unidades': -3}], [])
    assert r['ventas']['1'] == {'CERRO': -3}
```

- [ ] **Step 3: Ver fallar** — Run: `$PY -m pytest tests/test_fuentes_plex.py -v` — Expected: FAIL (ImportError).

- [ ] **Step 4: Implementar `fuentes_plex.py`:**

```python
"""Conector read-only al MySQL de Plex (ERP vivo).
DISCIPLINA: solo se consulta durante el refresco (cron diario + botón admin).
Las queries derivan del ETL probado de dashboard-bi; ante duda de schema
manda docs/erp_mysql_schema_legacy.md del comparador."""
from datetime import date, timedelta

from config import PLEX, SUCURSALES, VENTAS_VENTANA_DIAS, FUENTES_RUBROS, fuente_mysql_configurada

EXCLUIR = {'17', '33'}  # mismo criterio que data_loader

Q_PRODUCTOS = """
    SELECT m.IDProducto AS sku, m.Producto AS descripcion,
           l.Laboratorio AS laboratorio, r.Rubro AS rubro, m.Troquel AS troquel
    FROM medicamentos m
    LEFT JOIN laboratorios l ON l.CodLab = m.CodLab
    LEFT JOIN rubros r ON r.CodRubro = m.CodRubro
    WHERE r.Rubro IN ({placeholders})
"""

Q_EANS = """
    SELECT pc.IDProducto AS sku, pc.CodeBar AS ean
    FROM productoscodebars pc
"""

Q_VENTAS = """
    SELECT fl.IDProducto AS sku, fc.Sucursal AS sucursal,
           SUM(CASE WHEN fc.Tipo = 'NC' THEN -fl.Cantidad ELSE fl.Cantidad END) AS unidades
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


def _conn():
    import pymysql
    return pymysql.connect(
        host=PLEX['host'], port=PLEX['port'], user=PLEX['user'],
        password=PLEX['password'], database=PLEX['db'],
        connect_timeout=10, read_timeout=110,
        cursorclass=pymysql.cursors.DictCursor)


def _nombre_sucursal(sucursal):
    num = str(sucursal)
    if num in EXCLUIR:
        return None
    return SUCURSALES.get(num)


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
            'descripcion': str(r['descripcion'] or '').strip(),
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


def cargar():
    desde = (date.today() - timedelta(days=VENTAS_VENTANA_DIAS)).isoformat()
    conn = _conn()
    try:
        with conn.cursor() as cur:
            q_prod = Q_PRODUCTOS.format(placeholders=','.join(['%s'] * len(FUENTES_RUBROS)))
            cur.execute(q_prod, FUENTES_RUBROS)
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
```

Ajustar los nombres de columna de las Q_* según lo validado en el Step 1 (documentar cualquier delta en el reporte).

- [ ] **Step 5: Verificar** — Run: `$PY -m pytest tests/ -v` — Expected: todos PASS.

- [ ] **Step 6: Commit**

```bash
git add fuentes_plex.py tests/test_fuentes_plex.py
git commit -m "Fuentes: conector Plex read-only (catalogo, ventas 60d, stock por sucursal)"
```

---

### Task 5: Conector comparador (`fuentes_comparador.py`)

**Files:**
- Create: `fuentes_comparador.py`
- Test: `tests/test_fuentes_comparador.py`

**Interfaces:**
- Consumes: `config.COMPARADOR_DB_URL`.
- Produces: `cargar() -> dict` = `transformar(rows, ahora)` con estructura `{'precios': {sku: {'SUD': float|None, 'SUIZO': float|None}}, 'alfabeta': {sku: str}, 'mas_reciente': datetime|None, 'stale': bool}`; `configurada() -> bool`. Consumidas por Task 7.

- [ ] **Step 1: Test que falla** — crear `tests/test_fuentes_comparador.py`:

```python
from datetime import datetime, timedelta

from fuentes_comparador import transformar


def _row(sku, drog, precio, hace_horas, alfabeta=None):
    return {'sku': sku, 'drogueria': drog, 'precio': precio,
            'cod_alfabeta': alfabeta,
            'consultado_at': datetime(2026, 7, 3, 12) - timedelta(hours=hace_horas)}


def test_transformar_mapea_dds_a_sud_y_frescura():
    ahora = datetime(2026, 7, 3, 12)
    rows = [
        _row('555', 'DDS', 100.5, 2, alfabeta='7654321'),
        _row('555', 'SUIZO', 120.0, 3),
        _row('556', 'SUIZO', 80.0, 5),
    ]
    r = transformar(rows, ahora)
    assert r['precios']['555'] == {'SUD': 100.5, 'SUIZO': 120.0}
    assert r['precios']['556'] == {'SUD': None, 'SUIZO': 80.0}
    assert r['alfabeta']['555'] == '7654321'
    assert r['stale'] is False


def test_stale_si_todo_viejo():
    ahora = datetime(2026, 7, 3, 12)
    r = transformar([_row('1', 'DDS', 10.0, 72)], ahora)
    assert r['stale'] is True


def test_vacio():
    r = transformar([], datetime(2026, 7, 3, 12))
    assert r['precios'] == {} and r['mas_reciente'] is None and r['stale'] is True
```

- [ ] **Step 2: Ver fallar** — Run: `$PY -m pytest tests/test_fuentes_comparador.py -v` — Expected: FAIL (ImportError).

- [ ] **Step 3: Implementar `fuentes_comparador.py`:**

```python
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
```

- [ ] **Step 4: Verificar** — Run: `$PY -m pytest tests/ -v` — Expected: todos PASS.

- [ ] **Step 5: Commit**

```bash
git add fuentes_comparador.py tests/test_fuentes_comparador.py
git commit -m "Fuentes: conector comparador (precios DDS->SUD y SUIZO con guardia de frescura)"
```

---

### Task 6: Conector Quantio CD — cascada de matching + script de exploración

**Files:**
- Create: `fuentes_quantio.py`, `scripts/explorar_quantio.py`
- Test: `tests/test_fuentes_quantio.py`

**Interfaces:**
- Consumes: `config.CD_MYSQL`, `config.fuente_mysql_configurada`, `database.get_mapeo_cd`.
- Produces: `matchear_cd(filas_cd: list[dict], productos: dict, mapeo_manual: dict) -> tuple[dict[str,int], list[dict]]` (stock por sku, filas no matcheadas); `cargar_stock_cd() -> list[dict]` (filas crudas; lanza RuntimeError si `QUERY_STOCK` es None); `configurada() -> bool` (False mientras `QUERY_STOCK` sea None → fuente deshabilitada hasta Fase 0); constantes `QUERY_STOCK = None` y `CAMPOS = {'codigo': 'codigo', 'ean': 'ean', 'troquel': 'troquel', 'cantidad': 'cantidad'}` que la Task 11 fija con el schema real. Consumidas por Tasks 7, 8, 11.

- [ ] **Step 1: Test que falla** — crear `tests/test_fuentes_quantio.py`:

```python
from fuentes_quantio import matchear_cd

PRODUCTOS = {
    '555': {'ean': '7790000000001', 'troquel': '1234567'},
    '556': {'ean': '7790000000002', 'troquel': ''},
    '557': {'ean': '', 'troquel': '7654321'},
}


def test_cascada_codigo_directo():
    filas = [{'codigo': '555', 'ean': '', 'troquel': '', 'cantidad': 3}]
    stock, no_match = matchear_cd(filas, PRODUCTOS, {})
    assert stock == {'555': 3} and no_match == []


def test_cascada_ean():
    filas = [{'codigo': 'QX9', 'ean': '7790000000002', 'troquel': '', 'cantidad': 7}]
    stock, _ = matchear_cd(filas, PRODUCTOS, {})
    assert stock == {'556': 7}


def test_cascada_troquel():
    filas = [{'codigo': 'QX1', 'ean': '999', 'troquel': '7654321', 'cantidad': 2}]
    stock, _ = matchear_cd(filas, PRODUCTOS, {})
    assert stock == {'557': 2}


def test_cascada_mapeo_manual_y_no_match():
    filas = [
        {'codigo': 'QA', 'ean': '', 'troquel': '', 'cantidad': 5},
        {'codigo': 'QB', 'ean': '', 'troquel': '', 'cantidad': 1},
    ]
    stock, no_match = matchear_cd(filas, PRODUCTOS, {'QA': '555'})
    assert stock == {'555': 5}
    assert len(no_match) == 1 and no_match[0]['codigo'] == 'QB'


def test_cantidades_se_suman_y_cero_se_ignora():
    filas = [
        {'codigo': '555', 'ean': '', 'troquel': '', 'cantidad': 2},
        {'codigo': 'QX', 'ean': '7790000000001', 'troquel': '', 'cantidad': 3},
        {'codigo': '556', 'ean': '', 'troquel': '', 'cantidad': 0},
    ]
    stock, no_match = matchear_cd(filas, PRODUCTOS, {})
    assert stock == {'555': 5}
    assert no_match == []
```

- [ ] **Step 2: Ver fallar** — Run: `$PY -m pytest tests/test_fuentes_quantio.py -v` — Expected: FAIL (ImportError).

- [ ] **Step 3: Implementar `fuentes_quantio.py`:**

```python
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
```

- [ ] **Step 4: Crear `scripts/explorar_quantio.py`** (Fase 0; corre en el VPS con las env `CD_*`):

```python
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
```

- [ ] **Step 5: Verificar** — Run: `$PY -m pytest tests/ -v` — Expected: todos PASS.

- [ ] **Step 6: Commit**

```bash
git add fuentes_quantio.py scripts/explorar_quantio.py tests/test_fuentes_quantio.py
git commit -m "Fuentes: cascada de matching del CD + script de exploracion Fase 0"
```

---

### Task 7: Orquestador `fuentes.py` (memoria last-good + construir_catalogo + refrescar)

**Files:**
- Create: `fuentes.py`
- Test: `tests/test_fuentes_orquestador.py`

**Interfaces:**
- Consumes: `fuentes_plex.cargar/configurada`, `fuentes_comparador.cargar/configurada`, `fuentes_quantio.cargar_stock_cd/matchear_cd/configurada`, `data_loader.decidir_drogueria`, `data_loader.CACHE_FILE`, `database.set_fuente_estado/get_mapeo_cd`, `config.DATA_DIR`.
- Produces: `refrescar_fuentes() -> dict` con `{'ok': bool, 'productos': int, 'fuentes': {nombre: {'ok': bool, 'filas': int, 'error': str|None, 'desde_memoria': bool}}, 'no_matcheados': int}`; `construir_catalogo(plex, precios, stock_cd) -> list[dict]` (pura). También guarda el último `no_matcheados` en `DATA_DIR/cd_no_matcheados.json`. Consumidas por Task 8.

- [ ] **Step 1: Tests que fallan** — crear `tests/test_fuentes_orquestador.py`:

```python
import json
import os

import fuentes
from data_loader import decidir_drogueria


PLEX = {
    'productos': {
        '555': {'descripcion': 'SHAMPOO X', 'laboratorio': 'LAB A', 'rubro': 'Perfumería',
                'ean': '7790000000001', 'troquel': '1111111'},
        '556': {'descripcion': 'CREMA Y', 'laboratorio': 'LAB B', 'rubro': 'Accesorios',
                'ean': '7790000000002', 'troquel': ''},
    },
    'ventas': {'555': {'CERRO': 10, 'RECTA': 2}},
    'stock':  {'555': {'CERRO': 4}, '556': {'RECTA': 1}},
}
PRECIOS = {'precios': {'555': {'SUD': 100.0, 'SUIZO': 90.0}},
           'alfabeta': {'555': '7654321'}, 'mas_reciente': None, 'stale': False}


def test_construir_catalogo_estructura_identica():
    cat = fuentes.construir_catalogo(PLEX, PRECIOS, {'556': 8})
    por_sku = {p['sku']: p for p in cat}
    p = por_sku['555']
    # exactamente los campos que produce load_productos()
    assert set(p.keys()) == {'sku', 'ean', 'descripcion', 'laboratorio', 'rubro',
                             'stock_cd', 'drogueria', 'mejor_precio', 'drog_ext',
                             'troquel', 'troquel_pres', 'necesidad', 'stock_real', 'ventas'}
    assert p['drogueria'] == 'SUIZO' and p['mejor_precio'] == 90.0  # sin stock CD, mas barata
    assert p['troquel'] == '7654321'       # alfabeta del comparador -> export .dds
    assert p['troquel_pres'] == '1111111'  # troquel de Plex -> export Quantio
    assert p['necesidad'] == {'CERRO': 6, 'RECTA': 2}  # ventas - stock, min 0
    assert p['stock_real'] == {'CERRO': 4, 'RECTA': 0}
    assert por_sku['556']['stock_cd'] == 8
    assert por_sku['556']['drogueria'] == 'DROGUERIA RED'
    assert por_sku['556']['drogueria'] == 'DROGUERIA RED'
    assert por_sku['556']['mejor_precio'] is None


def test_refrescar_con_memoria_por_fuente(monkeypatch, tmp_path):
    llamadas = {'n': 0}

    def plex_ok():
        return PLEX

    def comparador_falla():
        llamadas['n'] += 1
        raise RuntimeError('conexion rechazada')

    monkeypatch.setattr(fuentes, '_DIR_MEMORIA', str(tmp_path))
    monkeypatch.setattr('fuentes_plex.configurada', lambda: True)
    monkeypatch.setattr('fuentes_plex.cargar', plex_ok)
    monkeypatch.setattr('fuentes_comparador.configurada', lambda: True)
    monkeypatch.setattr('fuentes_comparador.cargar', lambda: PRECIOS)
    monkeypatch.setattr('fuentes_quantio.configurada', lambda: False)

    r1 = fuentes.refrescar_fuentes()
    assert r1['ok'] is True and r1['productos'] == 2
    assert r1['fuentes']['comparador']['ok'] is True

    # ahora el comparador falla: usa la memoria last-good
    monkeypatch.setattr('fuentes_comparador.cargar', comparador_falla)
    r2 = fuentes.refrescar_fuentes()
    assert r2['ok'] is True
    assert r2['fuentes']['comparador']['ok'] is False
    assert r2['fuentes']['comparador']['desde_memoria'] is True
    assert r2['productos'] == 2  # catalogo igual se armo


def test_refrescar_falla_si_fuente_critica_sin_memoria(monkeypatch, tmp_path):
    monkeypatch.setattr(fuentes, '_DIR_MEMORIA', str(tmp_path))
    monkeypatch.setattr('fuentes_plex.configurada', lambda: True)
    monkeypatch.setattr('fuentes_plex.cargar',
                        lambda: (_ for _ in ()).throw(RuntimeError('down')))
    monkeypatch.setattr('fuentes_comparador.configurada', lambda: True)
    monkeypatch.setattr('fuentes_comparador.cargar', lambda: PRECIOS)
    monkeypatch.setattr('fuentes_quantio.configurada', lambda: False)
    r = fuentes.refrescar_fuentes()
    assert r['ok'] is False
    assert 'down' in (r['fuentes']['plex']['error'] or '')
```

- [ ] **Step 2: Ver fallar** — Run: `$PY -m pytest tests/test_fuentes_orquestador.py -v` — Expected: FAIL (ImportError).

- [ ] **Step 3: Implementar `fuentes.py`:**

```python
"""Orquestador de fuentes automáticas: refresco resiliente con memoria
last-good por fuente + ensamblado del catálogo (misma estructura que
data_loader.load_productos)."""
import json
import os
import pickle

import fuentes_comparador
import fuentes_plex
import fuentes_quantio
from config import DATA_DIR
from database import get_mapeo_cd, set_fuente_estado
from data_loader import decidir_drogueria

_DIR_MEMORIA = DATA_DIR  # override en tests
NO_MATCH_JSON = 'cd_no_matcheados.json'


def _ruta_memoria(fuente):
    return os.path.join(_DIR_MEMORIA, f'fuente_{fuente}.pkl')


def _cargar_con_memoria(nombre, fn_cargar):
    """Intenta la fuente; si falla usa el último resultado bueno guardado.
    Devuelve (datos|None, info_estado)."""
    try:
        datos = fn_cargar()
        with open(_ruta_memoria(nombre), 'wb') as f:
            pickle.dump(datos, f)
        return datos, {'ok': True, 'error': None, 'desde_memoria': False}
    except Exception as e:
        error = f'{type(e).__name__}: {e}'
        ruta = _ruta_memoria(nombre)
        if os.path.exists(ruta):
            with open(ruta, 'rb') as f:
                return pickle.load(f), {'ok': False, 'error': error, 'desde_memoria': True}
        return None, {'ok': False, 'error': error, 'desde_memoria': False}


def construir_catalogo(plex, precios, stock_cd):
    """Pura: datos de conectores -> lista de productos con la MISMA
    estructura que produce data_loader.load_productos()."""
    catalogo = []
    mapa_precios = precios.get('precios', {})
    alfabeta = precios.get('alfabeta', {})
    for sku, p in plex['productos'].items():
        pr = mapa_precios.get(sku, {})
        cant_cd = int(stock_cd.get(sku, 0))
        drogueria, mejor_precio, drog_ext, _ = decidir_drogueria(
            cant_cd, pr.get('SUD'), pr.get('SUIZO'))
        ventas = plex['ventas'].get(sku, {})
        stock = plex['stock'].get(sku, {})
        sucs = set(ventas) | set(stock)
        necesidad, stock_real, ventas_out = {}, {}, {}
        for s in sucs:
            v = int(ventas.get(s, 0))
            st = int(stock.get(s, 0))
            necesidad[s] = max(0, v - st)
            stock_real[s] = st
            ventas_out[s] = v
        catalogo.append({
            'sku':          sku,
            'ean':          p['ean'],
            'descripcion':  p['descripcion'],
            'laboratorio':  p['laboratorio'],
            'rubro':        p['rubro'],
            'stock_cd':     cant_cd,
            'drogueria':    drogueria,
            'mejor_precio': mejor_precio,
            'drog_ext':     drog_ext,
            'troquel':      alfabeta.get(sku, '0000000'),
            'troquel_pres': p['troquel'],
            'necesidad':    necesidad,
            'stock_real':   stock_real,
            'ventas':       ventas_out,
        })
    return catalogo


def refrescar_fuentes():
    """Orquesta el refresco. Plex y comparador son críticas (con memoria);
    Quantio es opcional (si está deshabilitada, stock CD = archivo manual
    vía el pipeline de data_loader... o vacío si tampoco hay archivo)."""
    import data_loader

    resumen = {'ok': False, 'productos': 0, 'fuentes': {}, 'no_matcheados': 0}

    plex, info = _cargar_con_memoria('plex', fuentes_plex.cargar) \
        if fuentes_plex.configurada() else (None, {'ok': False, 'error': 'sin configurar', 'desde_memoria': False})
    info['filas'] = len(plex['productos']) if plex else 0
    resumen['fuentes']['plex'] = info
    set_fuente_estado('plex', info['ok'], info['filas'], info['error'])

    precios, info_p = _cargar_con_memoria('comparador', fuentes_comparador.cargar) \
        if fuentes_comparador.configurada() else (None, {'ok': False, 'error': 'sin configurar', 'desde_memoria': False})
    info_p['filas'] = len(precios['precios']) if precios else 0
    resumen['fuentes']['comparador'] = info_p
    set_fuente_estado('comparador', info_p['ok'], info_p['filas'], info_p['error'])

    stock_cd, no_match = {}, []
    if fuentes_quantio.configurada() and plex:
        filas, info_q = _cargar_con_memoria('quantio', fuentes_quantio.cargar_stock_cd)
        if filas is not None:
            stock_cd, no_match = fuentes_quantio.matchear_cd(
                filas, plex['productos'], get_mapeo_cd())
        info_q['filas'] = len(stock_cd)
        resumen['fuentes']['quantio'] = info_q
        set_fuente_estado('quantio', info_q['ok'], info_q['filas'], info_q['error'])
    else:
        resumen['fuentes']['quantio'] = {'ok': False, 'error': 'sin configurar (Fase 0 pendiente)',
                                         'desde_memoria': False, 'filas': 0}

    if plex is None or precios is None:
        return resumen

    catalogo = construir_catalogo(plex, precios, stock_cd)
    resumen['productos'] = len(catalogo)
    resumen['no_matcheados'] = len(no_match)
    try:
        with open(os.path.join(_DIR_MEMORIA, NO_MATCH_JSON), 'w', encoding='utf-8') as f:
            json.dump(no_match, f, ensure_ascii=False)
    except OSError:
        pass

    # publicar: mismo pickle + catálogo en memoria del proceso
    with open(data_loader.CACHE_FILE, 'wb') as f:
        pickle.dump(catalogo, f)
    data_loader._productos = catalogo
    resumen['ok'] = True
    return resumen
```

- [ ] **Step 4: Verificar** — Run: `$PY -m pytest tests/ -v` — Expected: todos PASS.

- [ ] **Step 5: Commit**

```bash
git add fuentes.py tests/test_fuentes_orquestador.py
git commit -m "Fuentes: orquestador con memoria last-good por fuente y construir_catalogo equivalente"
```

---

### Task 8: Endpoints en app.py (refresco, CSV no-matcheados, upload mapeos)

**Files:**
- Modify: `app.py` (imports + 3 rutas + vista actualizar_datos)
- Test: `tests/test_fuentes_endpoints.py`

**Interfaces:**
- Consumes: `fuentes.refrescar_fuentes`, `database.get_fuentes_estado/agregar_mapeos_cd`, `config.FUENTES_CRON_TOKEN`, `fuentes.NO_MATCH_JSON`.
- Produces: `POST /api/fuentes/refrescar` (200 con resumen | 502 si ok=False | 403 sin auth; auth = sesión admin O header `X-Cron-Token` == FUENTES_CRON_TOKEN no vacío); `GET /fuentes/no-matcheados.csv` (admin); `POST /fuentes/mapeos` (admin, form-file `archivo` CSV `codigo_quantio,sku`); la vista `actualizar_datos` pasa `fuentes_estado` y `n_no_matcheados` al template. Consumidas por Task 9.

- [ ] **Step 1: Tests que fallan** — crear `tests/test_fuentes_endpoints.py`:

```python
import io
import json
import os


def test_refrescar_requiere_auth(client):
    assert client.post('/api/fuentes/refrescar').status_code == 403


def test_refrescar_con_token(client, monkeypatch):
    import app as app_module
    monkeypatch.setattr(app_module, 'FUENTES_CRON_TOKEN', 'tok123')
    monkeypatch.setattr(app_module, 'refrescar_fuentes',
                        lambda: {'ok': True, 'productos': 5, 'fuentes': {}, 'no_matcheados': 0})
    r = client.post('/api/fuentes/refrescar', headers={'X-Cron-Token': 'tok123'})
    assert r.status_code == 200 and r.get_json()['productos'] == 5
    r = client.post('/api/fuentes/refrescar', headers={'X-Cron-Token': 'malo'})
    assert r.status_code == 403


def test_refrescar_admin_y_fallo_502(admin, monkeypatch):
    import app as app_module
    monkeypatch.setattr(app_module, 'refrescar_fuentes',
                        lambda: {'ok': False, 'productos': 0, 'fuentes': {}, 'no_matcheados': 0})
    assert admin.post('/api/fuentes/refrescar').status_code == 502


def test_csv_no_matcheados(admin):
    import fuentes
    ruta = os.path.join(fuentes._DIR_MEMORIA, fuentes.NO_MATCH_JSON)
    with open(ruta, 'w', encoding='utf-8') as f:
        json.dump([{'codigo': 'Q1', 'ean': '779', 'troquel': '', 'cantidad': 4,
                    'descripcion': 'ALGO'}], f)
    r = admin.get('/fuentes/no-matcheados.csv')
    assert r.status_code == 200
    assert b'Q1' in r.data


def test_upload_mapeos(admin):
    data = {'archivo': (io.BytesIO('codigo_quantio,sku\nQ9,555\n'.encode()), 'mapeos.csv')}
    r = admin.post('/fuentes/mapeos', data=data, content_type='multipart/form-data',
                   follow_redirects=False)
    assert r.status_code == 302
    import database
    assert database.get_mapeo_cd().get('Q9') == '555'
```

- [ ] **Step 2: Ver fallar** — Run: `$PY -m pytest tests/test_fuentes_endpoints.py -v` — Expected: FAIL (404/AttributeError).

- [ ] **Step 3: Implementar en app.py** — sumar imports:

```python
from config import FUENTES_CRON_TOKEN
from database import get_fuentes_estado, agregar_mapeos_cd
from fuentes import refrescar_fuentes, NO_MATCH_JSON
import fuentes as fuentes_mod
```

Rutas nuevas (debajo de `actualizar_datos`):

```python
@app.route('/api/fuentes/refrescar', methods=['POST'])
def api_refrescar_fuentes():
    token = request.headers.get('X-Cron-Token', '')
    autorizado_cron = bool(FUENTES_CRON_TOKEN) and token == FUENTES_CRON_TOKEN
    if not autorizado_cron and session.get('rol') != 'admin':
        return jsonify({'error': 'Sin permiso'}), 403
    resumen = refrescar_fuentes()
    return jsonify(resumen), (200 if resumen['ok'] else 502)


@app.route('/fuentes/no-matcheados.csv')
@login_required
@admin_required
def fuentes_no_matcheados_csv():
    import csv as csv_mod
    import io as io_mod
    ruta = os.path.join(fuentes_mod._DIR_MEMORIA, NO_MATCH_JSON)
    filas = []
    if os.path.exists(ruta):
        import json as json_mod
        with open(ruta, encoding='utf-8') as f:
            filas = json_mod.load(f)
    buf = io_mod.StringIO()
    w = csv_mod.writer(buf)
    w.writerow(['codigo_quantio', 'ean', 'troquel', 'cantidad', 'sku'])
    for fila in filas:
        w.writerow([fila.get('codigo', ''), fila.get('ean', ''),
                    fila.get('troquel', ''), fila.get('cantidad', ''), ''])
    return Response(buf.getvalue().encode('utf-8-sig'), mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename="cd_no_matcheados.csv"'})


@app.route('/fuentes/mapeos', methods=['POST'])
@login_required
@admin_required
def fuentes_subir_mapeos():
    import csv as csv_mod
    import io as io_mod
    f = request.files.get('archivo')
    if not f or not f.filename:
        flash('No seleccionaste ningún archivo de mapeos.', 'warning')
        return redirect(url_for('actualizar_datos'))
    contenido = f.read().decode('utf-8-sig', errors='replace')
    pares = []
    for fila in csv_mod.DictReader(io_mod.StringIO(contenido)):
        codigo = (fila.get('codigo_quantio') or '').strip()
        sku = (fila.get('sku') or '').strip()
        if codigo and sku:
            pares.append((codigo, sku))
    n = agregar_mapeos_cd(pares)
    flash(f'{n} mapeos de CD cargados.', 'success')
    return redirect(url_for('actualizar_datos'))
```

Y en la vista `actualizar_datos()` (rama GET), antes del `return render_template`, agregar:

```python
    import json as json_mod
    ruta_nm = os.path.join(fuentes_mod._DIR_MEMORIA, NO_MATCH_JSON)
    n_no_match = 0
    if os.path.exists(ruta_nm):
        try:
            with open(ruta_nm, encoding='utf-8') as fnm:
                n_no_match = len(json_mod.load(fnm))
        except (OSError, ValueError):
            n_no_match = 0
```

y pasar al template: `fuentes_estado=get_fuentes_estado(), n_no_matcheados=n_no_match`.

- [ ] **Step 4: Verificar** — Run: `$PY -m pytest tests/ -v` — Expected: todos PASS.

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_fuentes_endpoints.py
git commit -m "Fuentes: endpoints de refresco (admin/cron), CSV de no-matcheados y upload de mapeos"
```

---

### Task 9: Pantalla "Actualizar datos" — sección de fuentes automáticas

**Files:**
- Modify: `templates/actualizar_datos.html`

**Interfaces:**
- Consumes: `fuentes_estado` (list de dicts: fuente, ultima_ok, filas, error, actualizado), `n_no_matcheados`; globals JS `toast`/`setLoading`; clases CSS del sistema (`metric-card`, `badge-comprado`, `badge-pendiente`, `badge-cancelado`, `btn-brand`, `btn-suave`).

- [ ] **Step 1: Agregar la sección arriba del contenido actual del template** (inmediatamente después del heading de la página; el bloque de carga manual existente queda debajo bajo un subtítulo "Fallback manual"):

```html
<h5 class="mb-3">Fuentes automáticas</h5>
<div class="row g-3 mb-3">
  {% set NOMBRES = {'plex': 'Plex ERP (catálogo, ventas, stock)',
                    'comparador': 'Comparador (precios SUD/SUIZO)',
                    'quantio': 'Quantio CD (stock depósito)'} %}
  {% set estados = {} %}
  {% for e in fuentes_estado %}{% set _ = estados.update({e.fuente: e}) %}{% endfor %}
  {% for clave, nombre in NOMBRES.items() %}
  {% set e = estados.get(clave) %}
  <div class="col-md-4">
    <div class="metric-card h-100">
      <div class="metric-label">{{ nombre }}</div>
      <div class="d-flex align-items-center gap-2 mt-1">
        {% if e and not e.error %}
          <span class="badge-comprado">OK</span>
        {% elif e and e.ultima_ok %}
          <span class="badge-pendiente">Con aviso</span>
        {% else %}
          <span class="badge-cancelado">Sin datos</span>
        {% endif %}
        <span class="small text-muted">{{ e.filas if e else 0 }} filas</span>
      </div>
      <div class="small text-muted mt-1">Última OK: {{ e.ultima_ok if e and e.ultima_ok else '—' }}</div>
      {% if e and e.error %}<div class="small" style="color: var(--peligro)">{{ e.error[:120] }}</div>{% endif %}
    </div>
  </div>
  {% endfor %}
</div>
<div class="d-flex gap-2 flex-wrap align-items-center mb-4">
  <button class="btn btn-sm btn-brand" onclick="refrescarFuentes(this)">Actualizar ahora</button>
  {% if n_no_matcheados %}
  <span class="badge-pendiente">{{ n_no_matcheados }} productos del CD sin matchear</span>
  <a class="btn btn-sm btn-suave" href="{{ url_for('fuentes_no_matcheados_csv') }}">↓ Descargar CSV</a>
  {% endif %}
  <form method="post" action="{{ url_for('fuentes_subir_mapeos') }}" enctype="multipart/form-data"
        class="d-flex gap-2 align-items-center">
    <input type="file" name="archivo" accept=".csv" class="form-control form-control-sm" style="width:230px">
    <button type="submit" class="btn btn-sm btn-suave">Subir mapeos CD</button>
  </form>
</div>
<h5 class="mb-3">Fallback manual</h5>
```

y en `{% block scripts %}` (crearlo si el template no lo tiene):

```html
{% block scripts %}
<script>
async function refrescarFuentes(btn) {
  setLoading(btn, true);
  try {
    const res = await fetch('/api/fuentes/refrescar', {method: 'POST'});
    const d = await res.json().catch(() => ({}));
    if (res.ok && d.ok) {
      toast(`Catálogo actualizado — ${d.productos} productos`, 'exito');
      setTimeout(() => location.reload(), 900);
      return;
    }
    toast(d.error || 'El refresco falló — revisá el estado de las fuentes', 'error');
    setTimeout(() => location.reload(), 1500);
  } catch (e) {
    toast('Error de conexión', 'error');
    setLoading(btn, false);
  }
}
</script>
{% endblock %}
```

(El `location.reload()` acá es deliberado y aceptable: es la pantalla de configuración del admin y necesita re-renderizar el estado server-side.)

- [ ] **Step 2: Verificar** — Run: `$PY -m pytest tests/ -v` — Expected: todos PASS. Grep: `grep -nE "#[0-9a-fA-F]{3,6}" templates/actualizar_datos.html` → sin matches.

- [ ] **Step 3: Commit**

```bash
git add templates/actualizar_datos.html
git commit -m "Fuentes: seccion de estado y refresco en Actualizar datos (fallback manual debajo)"
```

---

### Task 10 [VPS]: Fase 0 — exploración del schema Quantio (controlador + usuario)

**Pre-requisito:** el usuario cargó `PEDIDOS_CD_*` en el `.env` del VPS.

- [ ] Copiar el código actual al VPS (`git archive ui-redesign | ssh ... tar -C /opt/App-Pedidos`).
- [ ] Correr la exploración en un contenedor efímero (sin tocar el stack):

```bash
ssh -p 5930 root@179.43.123.251
cd /opt/farmacias-red-comparador
grep '^PEDIDOS_CD_' .env | sed 's/^PEDIDOS_//' > /tmp/cd.env
docker run --rm --env-file /tmp/cd.env -v /opt/App-Pedidos:/app -w /app \
  python:3.12-slim bash -c "pip install -q pymysql && python scripts/explorar_quantio.py" \
  > /tmp/quantio_schema.md
rm /tmp/cd.env
```

- [ ] Bajar `/tmp/quantio_schema.md`, guardarlo como `docs/quantio_cd_schema.md` en el repo local, analizarlo con el usuario: identificar tabla de stock, columna de cantidad e identificadores (¿IDProducto compartido con Plex? ¿EAN? ¿troquel?).
- [ ] Commit del doc: `git add docs/quantio_cd_schema.md && git commit -m "Fase 0: schema Quantio CD explorado"`.

---

### Task 11: Fijar la query Quantio según Fase 0

**Files:**
- Modify: `fuentes_quantio.py` (constantes `QUERY_STOCK` y `CAMPOS`)
- Test: `tests/test_fuentes_quantio.py` (agregar caso con filas con la forma real)

**Interfaces:** las de Task 6, con `configurada()` pasando a True cuando hay env.

- [ ] Con `docs/quantio_cd_schema.md` en mano, escribir `QUERY_STOCK` (SELECT read-only de la tabla de stock del CD con las columnas reales, alias a `codigo/ean/troquel/cantidad` según `CAMPOS`) y ajustar `CAMPOS` a los nombres reales (poner `None` en los identificadores que Quantio no tenga).
- [ ] Agregar a `tests/test_fuentes_quantio.py` un test con 2-3 filas con la forma REAL del schema (valores anonimizados del doc) pasando por `cargar_stock_cd`-shape → `matchear_cd`, verificando el camino de la cascada que aplica según lo descubierto.
- [ ] Run: `$PY -m pytest tests/ -v` → PASS. Commit: `git add fuentes_quantio.py tests/test_fuentes_quantio.py && git commit -m "Fuentes: query de stock CD segun schema real de Quantio"`.

---

### Task 12 [VPS]: Infraestructura de deploy (rol RO, tokens, compose, cron)

- [ ] **Rol read-only en el Postgres del comparador** (password generado en el VPS, nunca en chat):

```bash
cd /opt/farmacias-red-comparador
PW=$(openssl rand -hex 24)
docker compose -f docker-compose.prod.yml exec -T postgres psql -U "$POSTGRES_USER_DEL_ENV" -d farmacias_red <<SQL
CREATE ROLE pedidos_ro LOGIN PASSWORD '$PW';
GRANT CONNECT ON DATABASE farmacias_red TO pedidos_ro;
GRANT USAGE ON SCHEMA public TO pedidos_ro;
GRANT SELECT ON productos, precios_snapshot TO pedidos_ro;
SQL
echo "PEDIDOS_COMPARADOR_DB_URL=postgresql://pedidos_ro:$PW@postgres:5432/farmacias_red" >> .env
echo "PEDIDOS_FUENTES_CRON_TOKEN=$(openssl rand -hex 24)" >> .env
```

- [ ] **Compose** (repo comparador, `docker-compose.prod.yml`, servicio `pedidos` → environment) agregar:

```yaml
      PLEX_HOST: ${PEDIDOS_PLEX_HOST:-}
      PLEX_PORT: ${PEDIDOS_PLEX_PORT:-3306}
      PLEX_USER: ${PEDIDOS_PLEX_USER:-}
      PLEX_PASSWORD: ${PEDIDOS_PLEX_PASSWORD:-}
      PLEX_DB: ${PEDIDOS_PLEX_DB:-}
      CD_HOST: ${PEDIDOS_CD_HOST:-}
      CD_PORT: ${PEDIDOS_CD_PORT:-3306}
      CD_USER: ${PEDIDOS_CD_USER:-}
      CD_PASSWORD: ${PEDIDOS_CD_PASSWORD:-}
      CD_DB: ${PEDIDOS_CD_DB:-}
      COMPARADOR_DB_URL: ${PEDIDOS_COMPARADOR_DB_URL:-}
      VENTAS_VENTANA_DIAS: ${PEDIDOS_VENTAS_VENTANA_DIAS:-60}
      FUENTES_CRON_TOKEN: ${PEDIDOS_FUENTES_CRON_TOKEN:-}
```

más el bloque equivalente comentado en `.env.prod.example` (sin valores). Commit en el repo comparador (rama `feat/hostear-app-pedidos`).

- [ ] **Cron** (repo comparador, crear `deploy/cron/pedidos-fuentes`):

```
# Refresco diario del catalogo de App-Pedidos desde las fuentes (10:30,
# despues del sync de precios del comparador). El token vive en el .env.
30 10 * * * root . /opt/farmacias-red-comparador/.env 2>/dev/null; curl -fsS -m 180 -X POST -H "X-Cron-Token: ${PEDIDOS_FUENTES_CRON_TOKEN}" https://pedidos.farmaciasred.com/api/fuentes/refrescar >> /var/log/pedidos-fuentes.log 2>&1
```

Instalar: `sudo cp deploy/cron/pedidos-fuentes /etc/cron.d/ && sudo chmod 0644 /etc/cron.d/pedidos-fuentes`.

- [ ] Redeploy del servicio: `git archive` del código nuevo → `/opt/App-Pedidos` → `docker compose -f docker-compose.prod.yml up -d --build pedidos` → health 200 → comparador intacto (IDs).

---

### Task 13 [VPS]: Validación de aceptación y primera corrida real

**Files:**
- Create: `scripts/comparar_catalogos.py`

- [ ] Crear `scripts/comparar_catalogos.py` (correr DENTRO del contenedor, donde están las env y los archivos manuales del volumen):

```python
"""Aceptación: compara el catálogo por FUENTES vs el catálogo por ARCHIVOS.
Uso: docker compose -f docker-compose.prod.yml exec pedidos python scripts/comparar_catalogos.py"""
import random

import data_loader
import fuentes
import fuentes_comparador
import fuentes_plex
import fuentes_quantio
from database import get_mapeo_cd

archivos = data_loader.load_productos()
por_sku_arch = {p['sku']: p for p in archivos}
print(f'Catálogo por ARCHIVOS: {len(archivos)} productos')

plex = fuentes_plex.cargar()
precios = fuentes_comparador.cargar()
stock_cd = {}
if fuentes_quantio.configurada():
    stock_cd, no_match = fuentes_quantio.matchear_cd(
        fuentes_quantio.cargar_stock_cd(), plex['productos'], get_mapeo_cd())
    print(f'Stock CD: {len(stock_cd)} matcheados, {len(no_match)} sin match')
cat = fuentes.construir_catalogo(plex, precios, stock_cd)
por_sku_fue = {p['sku']: p for p in cat}
print(f'Catálogo por FUENTES : {len(cat)} productos')

comunes = sorted(set(por_sku_arch) & set(por_sku_fue))
solo_arch = len(por_sku_arch) - len(comunes)
solo_fue = len(por_sku_fue) - len(comunes)
print(f'En común: {len(comunes)} | solo archivos: {solo_arch} | solo fuentes: {solo_fue}')

muestra = random.sample(comunes, min(15, len(comunes)))
print('\nsku | drog archivos->fuentes | precio a->f | stockCD a->f | ventas CERRO a->f')
for sku in muestra:
    a, f = por_sku_arch[sku], por_sku_fue[sku]
    print(f"{sku} | {a['drogueria'] or '-'}->{f['drogueria'] or '-'} | "
          f"{a['mejor_precio']}->{f['mejor_precio']} | {a['stock_cd']}->{f['stock_cd']} | "
          f"{a['ventas'].get('CERRO', 0)}->{f['ventas'].get('CERRO', 0)}")
```

Commit: `git add scripts/comparar_catalogos.py && git commit -m "Fuentes: script de aceptacion catalogo archivos vs fuentes"`.

- [ ] Deploy del script + correrlo en el VPS. **Revisar los números CON el usuario**: deltas de cantidad de productos explicables (archivos viejos vs datos frescos), precios de la muestra coincidentes o con drift entendible, ventas/stock razonables.
- [ ] Con el visto bueno: primera corrida real (`POST /api/fuentes/refrescar` desde el botón de la UI), smoke por la web (consolidado y generar orden con el catálogo nuevo), verificar tarjetas de estado en verde.
- [ ] Actualizar el ledger y avisar al usuario: los archivos manuales quedan como fallback; el cron corre mañana 10:30.

---

## Self-Review (hecho al escribir el plan)

- **Cobertura del spec:** decidir_drogueria compartida → T1; tablas estado/mapeo → T2; env/deps → T3; conector Plex con queries del ETL y validación contra doc legacy → T4; comparador con DDS→SUD, DISTINCT ON, alfabeta, stale 48h → T5; Quantio cascada + exploración → T6/T10/T11; orquestador con memoria last-good, resiliencia y pickle idéntico → T7; endpoint dual-auth + CSV + mapeos → T8; pantalla → T9; rol RO/compose/.env.example/cron → T12; aceptación comparar catálogos → T13. Fallback manual intacto (ningún task borra el pipeline de archivos). Sin huecos.
- **Placeholders:** `QUERY_STOCK = None` es comportamiento definido (fuente deshabilitada), no placeholder; su valor definitivo es el entregable de T11 con insumo de T10 — dependencia declarada entre tareas, con el criterio de escritura explícito.
- **Consistencia de tipos/nombres:** `transformar/cargar/configurada` uniformes en los 3 conectores; `refrescar_fuentes()` resumen consumido igual en T8 test y T9 JS; claves de estructura del catálogo idénticas entre T7 test, spec y data_loader; `_DIR_MEMORIA`/`NO_MATCH_JSON` compartidos entre T7 y T8.
