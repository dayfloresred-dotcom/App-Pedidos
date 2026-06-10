# App Pedidos Farmacias Red — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Flask web app that lets 22 pharmacy branches submit replenishment requests, and lets the admin consolidate, manage and export purchase orders to SUD and SUIZO drugstores.

**Architecture:** Python Flask backend with SQLite for orders, product data loaded at startup from existing CSV files, Bootstrap 5 frontend with vanilla JS for dynamic search. Auth via Flask sessions with Werkzeug password hashing.

**Tech Stack:** Python 3.10+, Flask, Flask-Login, Flask-Mail, Werkzeug, SQLite3, Bootstrap 5 (CDN), openpyxl

---

## File Structure

```
C:\Users\d.dartayet\Desktop\Tio Clau\App Pedidos\
├── app.py                  # Flask app, all routes
├── config.py               # Paths, mail config, sucursal list
├── database.py             # SQLite init + all DB helpers
├── data_loader.py          # Load products from CSV files into memory
├── mail_service.py         # Send notification emails
├── export_service.py       # Generate .arg (SUIZO) and .dds (SUD) files
├── requirements.txt
├── templates/
│   ├── base.html           # Navbar + layout shell
│   ├── login.html
│   ├── nueva_solicitud.html
│   ├── mis_pedidos.html
│   ├── confirmado.html
│   ├── consolidado.html
│   ├── generar_orden.html
├── static/
│   └── style.css
└── docs/
    ├── 2026-06-08-app-pedidos-design.md
    └── 2026-06-08-app-pedidos-plan.md
```

**Data files (read-only, already exist):**
```
C:\Users\d.dartayet\Desktop\Tio Clau\Necesidad Sucursales\
├── Presupuesto 04-06-26.csv
├── Listado de Stock 6-4.csv
├── Stock CD.csv
├── precios Sud.txt
├── precios perfu Suizo.xls
└── precios insumos Suizo.xls
```

---

## Task 1: Project setup and dependencies

**Files:**
- Create: `App Pedidos/requirements.txt`
- Create: `App Pedidos/config.py`

- [ ] **Step 1: Create requirements.txt**

```
flask==3.0.3
flask-login==0.6.3
flask-mail==0.10.0
werkzeug==3.0.3
openpyxl==3.1.2
xlrd==2.0.1
```

- [ ] **Step 2: Install dependencies**

Run from `C:\Users\d.dartayet\Desktop\Tio Clau\App Pedidos\`:
```bash
pip install -r requirements.txt --break-system-packages
```
Expected: All packages install without errors.

- [ ] **Step 3: Create config.py**

```python
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.dirname(BASE_DIR), 'Necesidad Sucursales')
DB_PATH  = os.path.join(BASE_DIR, 'pedidos.db')

SECRET_KEY = 'farmacias-red-2026-secret'

# Mail
MAIL_SERVER   = 'smtp.gmail.com'
MAIL_PORT     = 587
MAIL_USE_TLS  = True
MAIL_USERNAME = ''   # Set before running: Gmail address used to send
MAIL_PASSWORD = ''   # App password from Google Account settings
MAIL_ADMIN    = 'jenarraigada.red@gmail.com'

# Data file paths
PRESUPUESTO_CSV   = os.path.join(DATA_DIR, 'Presupuesto 04-06-26.csv')
LISTADO_STOCK_CSV = os.path.join(DATA_DIR, 'Listado de Stock 6-4.csv')
STOCK_CD_CSV      = os.path.join(DATA_DIR, 'Stock CD.csv')
PRECIOS_SUD_TXT   = os.path.join(DATA_DIR, 'precios Sud.txt')
PRECIOS_SUIZO_PERFU = os.path.join(DATA_DIR, 'precios perfu Suizo.xls')
PRECIOS_SUIZO_INS   = os.path.join(DATA_DIR, 'precios insumos Suizo.xls')

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
```

---

## Task 2: Database setup

**Files:**
- Create: `App Pedidos/database.py`

- [ ] **Step 1: Create database.py with schema and helpers**

```python
import sqlite3
from datetime import datetime
from config import DB_PATH

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            rol           TEXT NOT NULL CHECK(rol IN ('sucursal','admin'))
        );
        CREATE TABLE IF NOT EXISTS solicitudes (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            numero           TEXT UNIQUE NOT NULL,
            sucursal         TEXT NOT NULL,
            creado_por       TEXT NOT NULL,
            fecha_solicitud  TEXT NOT NULL,
            fecha_compra     TEXT,
            estado           TEXT NOT NULL DEFAULT 'pendiente'
        );
        CREATE TABLE IF NOT EXISTS items_solicitud (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            solicitud_id  INTEGER NOT NULL REFERENCES solicitudes(id),
            sku           TEXT NOT NULL,
            ean           TEXT,
            descripcion   TEXT NOT NULL,
            laboratorio   TEXT,
            cantidad      INTEGER NOT NULL,
            drogueria     TEXT
        );
    ''')
    conn.commit()
    conn.close()

def generar_numero():
    conn = get_db()
    row = conn.execute('SELECT COUNT(*) as c FROM solicitudes').fetchone()
    n = row['c'] + 1
    conn.close()
    return f'SOL-{n:06d}'

def crear_solicitud(sucursal, creado_por, items):
    conn = get_db()
    numero = generar_numero()
    fecha  = datetime.now().strftime('%d/%m/%Y %H:%M')
    conn.execute(
        'INSERT INTO solicitudes (numero, sucursal, creado_por, fecha_solicitud) VALUES (?,?,?,?)',
        (numero, sucursal, creado_por, fecha)
    )
    sol_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
    for it in items:
        conn.execute(
            'INSERT INTO items_solicitud (solicitud_id, sku, ean, descripcion, laboratorio, cantidad, drogueria) VALUES (?,?,?,?,?,?,?)',
            (sol_id, it['sku'], it.get('ean',''), it['descripcion'], it.get('laboratorio',''), it['cantidad'], it.get('drogueria',''))
        )
    conn.commit()
    conn.close()
    return numero, sol_id

def get_solicitudes_sucursal(sucursal):
    conn = get_db()
    rows = conn.execute(
        'SELECT * FROM solicitudes WHERE sucursal=? ORDER BY id DESC', (sucursal,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_solicitud_detalle(sol_id):
    conn = get_db()
    sol   = conn.execute('SELECT * FROM solicitudes WHERE id=?', (sol_id,)).fetchone()
    items = conn.execute('SELECT * FROM items_solicitud WHERE solicitud_id=?', (sol_id,)).fetchall()
    conn.close()
    if not sol:
        return None, []
    return dict(sol), [dict(i) for i in items]

def get_todas_solicitudes(sucursal_filtro=None, lab_filtro=None, drogueria_filtro=None):
    conn = get_db()
    query = 'SELECT s.*, COUNT(i.id) as n_items FROM solicitudes s LEFT JOIN items_solicitud i ON i.solicitud_id=s.id'
    params = []
    wheres = []
    if sucursal_filtro:
        wheres.append('s.sucursal=?'); params.append(sucursal_filtro)
    if wheres:
        query += ' WHERE ' + ' AND '.join(wheres)
    query += ' GROUP BY s.id ORDER BY s.id DESC'
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_consolidado(sucursal_filtro=None, lab_filtro=None, drogueria_filtro=None):
    conn = get_db()
    query = '''
        SELECT i.sku, i.ean, i.descripcion, i.laboratorio, i.drogueria,
               SUM(i.cantidad) as total,
               GROUP_CONCAT(DISTINCT s.sucursal) as sucursales
        FROM items_solicitud i
        JOIN solicitudes s ON s.id=i.solicitud_id
        WHERE s.estado='pendiente'
    '''
    params = []
    if sucursal_filtro:
        query += ' AND s.sucursal=?'; params.append(sucursal_filtro)
    if lab_filtro:
        query += ' AND LOWER(i.laboratorio) LIKE ?'; params.append(f'%{lab_filtro.lower()}%')
    if drogueria_filtro:
        query += ' AND i.drogueria=?'; params.append(drogueria_filtro)
    query += ' GROUP BY i.sku ORDER BY total DESC'
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_detalle_por_sucursal(sku):
    conn = get_db()
    rows = conn.execute('''
        SELECT s.sucursal, i.cantidad
        FROM items_solicitud i
        JOIN solicitudes s ON s.id=i.solicitud_id
        WHERE i.sku=? AND s.estado='pendiente'
        ORDER BY s.sucursal
    ''', (sku,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def marcar_comprado(sol_ids, fecha_compra):
    conn = get_db()
    for sid in sol_ids:
        conn.execute(
            'UPDATE solicitudes SET estado=?, fecha_compra=? WHERE id=?',
            ('comprado', fecha_compra, sid)
        )
    conn.commit()
    conn.close()
```

- [ ] **Step 2: Verify DB creates correctly**

```python
# Run in Python shell from App Pedidos/ folder:
# python3 -c "from database import init_db; init_db(); print('OK')"
```
Expected: `OK` printed, `pedidos.db` file created.

---

## Task 3: Product data loader

**Files:**
- Create: `App Pedidos/data_loader.py`

- [ ] **Step 1: Create data_loader.py**

```python
import csv, re
from config import (PRESUPUESTO_CSV, LISTADO_STOCK_CSV, STOCK_CD_CSV,
                    PRECIOS_SUD_TXT, PRECIOS_SUIZO_PERFU, PRECIOS_SUIZO_INS,
                    SUCURSALES)

RUBROS  = {'Perfumería', 'Accesorios'}
EXCLUIR = {'17', '33'}

_productos = None   # list of dicts, loaded once at startup

def _extract_num(s):
    return s.replace('Suc. ','').replace('SUC','').strip()

def _load_eans():
    eans = {}
    with open(LISTADO_STOCK_CSV, encoding='latin-1') as f:
        for i, line in enumerate(f):
            if i < 12: continue
            row = line.rstrip().split(';')
            if len(row) > 2 and row[0].strip():
                eans[row[0].strip()] = row[2].strip()
    return eans

def _load_cd_stock():
    cd = set()
    with open(STOCK_CD_CSV, encoding='latin-1') as f:
        for row in csv.DictReader(f, delimiter=';'):
            try:
                if float(row['Cantidad'].replace(',','.')) > 0:
                    cd.add(row['idProducto'].strip())
            except: pass
    return cd

def _load_sud_prices():
    prices = {}
    with open(PRECIOS_SUD_TXT, encoding='utf-8-sig') as f:
        for line in f:
            if not line.startswith('D'): continue
            eans = re.findall(r'HE(\d{13})', line)
            try: price = int(line[163:175]) / 100
            except: continue
            if price <= 0: continue
            for ean in eans:
                prices[ean] = price
    return prices

def _load_suizo_prices():
    prices = {}
    for fname in [PRECIOS_SUIZO_PERFU, PRECIOS_SUIZO_INS]:
        with open(fname, encoding='latin-1') as f:
            for i, line in enumerate(f):
                if i == 0: continue
                cols = line.rstrip().split('\t')
                if len(cols) < 5: continue
                try:
                    p = float((cols[4] or cols[3]).strip('"').replace(',','.').strip())
                except: continue
                if p < 1: continue
                for c in [1, 13, 14, 15, 16, 17]:
                    if c < len(cols):
                        ean = cols[c].strip('"').strip()
                        if ean and len(ean) >= 7:
                            prices[ean] = p
    return prices

def _load_troqueles_sud():
    """Map EAN -> troquel (7 chars) from SUD price file for .dds export."""
    troqueles = {}
    with open(PRECIOS_SUD_TXT, encoding='utf-8-sig') as f:
        for line in f:
            if not line.startswith('D'): continue
            troquel = str(int(line[1:19]))[-7:].zfill(7)
            eans = re.findall(r'HE(\d{13})', line)
            for ean in eans:
                troqueles[ean] = troquel
    return troqueles

def load_productos():
    global _productos
    if _productos is not None:
        return _productos

    eans      = _load_eans()
    cd_stock  = _load_cd_stock()
    sud_p     = _load_sud_prices()
    suizo_p   = _load_suizo_prices()
    troqueles = _load_troqueles_sud()

    # Build suc_vend and suc_stock column indices
    headers = []
    suc_vend  = {}  # suc_name -> col index
    suc_stock = {}

    productos = []
    with open(PRESUPUESTO_CSV, encoding='latin-1') as f:
        reader = csv.reader(f, delimiter=';')
        for i, row in enumerate(reader):
            if i == 2:
                headers = row
                for idx, h in enumerate(headers):
                    if h.startswith('Cajas Vend'):
                        num = _extract_num(h.replace('Cajas Vend. ','').replace('Cajas Vend ',''))
                        if num not in EXCLUIR and num in SUCURSALES:
                            suc_vend[SUCURSALES[num]] = idx
                    elif h.startswith('Cajas Stock'):
                        num = _extract_num(h.replace('Cajas Stock ',''))
                        if num not in EXCLUIR and num in SUCURSALES:
                            suc_stock[SUCURSALES[num]] = idx
            elif i > 2 and row and len(row) > 5 and row[3] in RUBROS:
                sku = row[0].strip()
                ean = eans.get(sku, '' if 'E+' in row[2] else row[2])
                p_sud   = sud_p.get(ean)
                p_suizo = suizo_p.get(ean)
                if p_sud and p_suizo:
                    drogueria   = 'SUD' if p_sud <= p_suizo else 'SUIZO'
                    mejor_precio = min(p_sud, p_suizo)
                elif p_sud:
                    drogueria, mejor_precio = 'SUD', p_sud
                elif p_suizo:
                    drogueria, mejor_precio = 'SUIZO', p_suizo
                else:
                    drogueria, mejor_precio = '', None

                # Stock/necesidad per sucursal
                suc_data = {}
                for sname, v_idx in suc_vend.items():
                    s_idx = suc_stock.get(sname)
                    try: ventas = int(float(row[v_idx].replace(',','.'))) if row[v_idx].strip() else 0
                    except: ventas = 0
                    try: stock = int(float(row[s_idx].replace(',','.'))) if s_idx and row[s_idx].strip() else 0
                    except: stock = 0
                    suc_data[sname] = max(0, ventas - stock)

                productos.append({
                    'sku':          sku,
                    'ean':          ean,
                    'descripcion':  row[4],
                    'laboratorio':  row[5],
                    'rubro':        row[3],
                    'stock_cd':     'SI' if sku in cd_stock else 'NO',
                    'drogueria':    drogueria,
                    'mejor_precio': mejor_precio,
                    'troquel':      troqueles.get(ean, '0000000'),
                    'necesidad':    suc_data,
                })

    _productos = productos
    return _productos

def buscar_productos(q='', laboratorio='', sucursal=None):
    """Return filtered product list. sucursal filters necesidad > 0."""
    prods = load_productos()
    result = []
    q   = q.lower().strip()
    lab = laboratorio.lower().strip()
    for p in prods:
        if lab and lab not in p['laboratorio'].lower():
            continue
        if q and q not in p['descripcion'].lower() and q not in p['ean']:
            continue
        if sucursal and sucursal != 'admin':
            nec = p['necesidad'].get(sucursal, 0)
        else:
            nec = 0
        result.append({**p, 'necesidad_suc': nec})
    return result

def get_laboratorios():
    prods = load_productos()
    return sorted(set(p['laboratorio'] for p in prods if p['laboratorio']))
```

- [ ] **Step 2: Verify loader works**

```bash
# From App Pedidos/ directory:
python3 -c "
from data_loader import load_productos, buscar_productos
prods = load_productos()
print(f'Productos cargados: {len(prods)}')
r = buscar_productos(laboratorio='unilever')
print(f'Unilever: {len(r)} productos')
print(r[0])
"
```
Expected: `Productos cargados: 12787`, some Unilever products printed.

---

## Task 4: Authentication + user seeding

**Files:**
- Create: `App Pedidos/auth.py`

- [ ] **Step 1: Create auth.py**

```python
from functools import wraps
from flask import session, redirect, url_for, abort
from werkzeug.security import generate_password_hash, check_password_hash
from database import get_db, init_db
from config import SUCURSAL_NAMES, ADMIN_USER

def seed_users():
    """Create default users if they don't exist."""
    conn = get_db()
    existing = {r['username'] for r in conn.execute('SELECT username FROM usuarios').fetchall()}

    to_create = []
    # Admin
    if ADMIN_USER not in existing:
        to_create.append((ADMIN_USER, generate_password_hash('admin123'), 'admin'))
    # Each sucursal
    for name in SUCURSAL_NAMES:
        if name not in existing:
            pwd = name.lower().replace(' ','') + '123'
            to_create.append((name, generate_password_hash(pwd), 'sucursal'))

    if to_create:
        conn.executemany(
            'INSERT INTO usuarios (username, password_hash, rol) VALUES (?,?,?)',
            to_create
        )
        conn.commit()
    conn.close()

def verify_user(username, password):
    """Returns (username, rol) or None."""
    conn = get_db()
    row = conn.execute(
        'SELECT * FROM usuarios WHERE username=?', (username,)
    ).fetchone()
    conn.close()
    if row and check_password_hash(row['password_hash'], password):
        return row['username'], row['rol']
    return None

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get('rol') != 'admin':
            abort(403)
        return f(*args, **kwargs)
    return decorated
```

---

## Task 5: Mail service

**Files:**
- Create: `App Pedidos/mail_service.py`

- [ ] **Step 1: Create mail_service.py**

```python
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from config import MAIL_SERVER, MAIL_PORT, MAIL_USERNAME, MAIL_PASSWORD, MAIL_ADMIN

def enviar_notificacion(numero, sucursal, items):
    """Send email notification to admin when a new order is created."""
    if not MAIL_USERNAME or not MAIL_PASSWORD:
        print(f'[MAIL] Skipped (not configured). Order: {numero}')
        return

    body_lines = [
        f'Nueva solicitud recibida: <b>{numero}</b>',
        f'Sucursal: <b>{sucursal}</b>',
        f'Productos solicitados: <b>{len(items)}</b>',
        '<br><table border="1" cellpadding="4" style="border-collapse:collapse">',
        '<tr><th>EAN</th><th>Producto</th><th>Laboratorio</th><th>Cantidad</th></tr>',
    ]
    for it in items:
        body_lines.append(
            f'<tr><td>{it.get("ean","")}</td><td>{it["descripcion"]}</td>'
            f'<td>{it.get("laboratorio","")}</td><td>{it["cantidad"]}</td></tr>'
        )
    body_lines.append('</table>')

    msg = MIMEMultipart('alternative')
    msg['Subject'] = f'[Farmacias Red] Nueva solicitud {numero} — {sucursal}'
    msg['From']    = MAIL_USERNAME
    msg['To']      = MAIL_ADMIN
    msg.attach(MIMEText('\n'.join(body_lines), 'html'))

    try:
        with smtplib.SMTP(MAIL_SERVER, MAIL_PORT) as s:
            s.starttls()
            s.login(MAIL_USERNAME, MAIL_PASSWORD)
            s.sendmail(MAIL_USERNAME, MAIL_ADMIN, msg.as_string())
        print(f'[MAIL] Sent notification for {numero}')
    except Exception as e:
        print(f'[MAIL] Error sending: {e}')
```

---

## Task 6: Export service (.arg and .dds)

**Files:**
- Create: `App Pedidos/export_service.py`

- [ ] **Step 1: Create export_service.py**

```python
def generar_suizo(items):
    """
    SUIZO .arg format:
    EAN (13 chars) + 30 spaces + quantity (3 digits zero-padded)
    Total line length: 46 chars
    """
    lines = []
    for it in items:
        ean = (it.get('ean') or '').ljust(13)[:13]
        qty = str(it['cantidad']).zfill(3)
        lines.append(f"{ean}{'':30}{qty}")
    return '\n'.join(lines)

def generar_sud(items):
    """
    SUD .dds format:
    EAN (13) + troquel (7) + product name (33, truncated/padded) + quantity
    Total line length: 53 + len(qty)
    """
    lines = []
    for it in items:
        ean     = (it.get('ean') or '').ljust(13)[:13]
        troquel = (it.get('troquel') or '0000000').zfill(7)[:7]
        nombre  = (it.get('descripcion') or '').ljust(33)[:33]
        qty     = str(it['cantidad'])
        lines.append(f"{ean}{troquel}{nombre}{qty}")
    return '\n'.join(lines)
```

- [ ] **Step 2: Verify format output**

```python
# python3 -c "
# from export_service import generar_suizo, generar_sud
# items = [{'ean':'7796285277154','troquel':'4511883','descripcion':'AXE AER BLACK X 97G','cantidad':4}]
# s = generar_suizo(items)
# print(repr(s))
# print(f'line len: {len(s)}')
# d = generar_sud(items)
# print(repr(d))
# print(f'line len: {len(d)}')
# "
```
Expected: SUIZO line 46 chars, SUD line 54 chars.

---

## Task 7: Base templates + login

**Files:**
- Create: `App Pedidos/templates/base.html`
- Create: `App Pedidos/templates/login.html`
- Create: `App Pedidos/static/style.css`

- [ ] **Step 1: Create static/style.css**

```css
body { font-size: 14px; }
.navbar-brand { font-weight: 600; }
.table th { background: #f8f9fa; font-size: 12px; }
.table td { font-size: 13px; vertical-align: middle; }
.qty-input { width: 70px; text-align: center; }
.badge-sud { background: #fef3c7; color: #92400e; }
.badge-suizo { background: #ede9fe; color: #5b21b6; }
.badge-pendiente { background: #fef3c7; color: #92400e; }
.badge-comprado { background: #dcfce7; color: #166534; }
.chip-suc { background: #e8f4ec; color: #2a7a3b; font-size: 11px; padding: 2px 7px; border-radius: 10px; margin: 1px; display: inline-block; }
.sol-number { color: #0d6efd; font-weight: 600; }
.filter-bar { background: #f8f9fa; padding: 12px 0; margin-bottom: 16px; border-radius: 8px; }
```

- [ ] **Step 2: Create templates/base.html**

```html
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Farmacias Red — Pedidos</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
  <link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">
</head>
<body>
<nav class="navbar navbar-expand-lg" style="background:#2c6e8a">
  <div class="container-fluid">
    <span class="navbar-brand text-white">Farmacias Red</span>
    <div class="d-flex gap-2">
      {% if session.get('username') %}
        {% if session.get('rol') == 'admin' or True %}
          <a href="{{ url_for('nueva_solicitud') }}" class="btn btn-sm {% if request.endpoint == 'nueva_solicitud' %}btn-light{% else %}btn-outline-light{% endif %}">Nueva solicitud</a>
          <a href="{{ url_for('mis_pedidos') }}" class="btn btn-sm {% if request.endpoint == 'mis_pedidos' %}btn-light{% else %}btn-outline-light{% endif %}">Mis pedidos</a>
        {% endif %}
        {% if session.get('rol') == 'admin' %}
          <a href="{{ url_for('consolidado') }}" class="btn btn-sm {% if request.endpoint == 'consolidado' %}btn-light{% else %}btn-outline-light{% endif %}">Consolidado</a>
          <a href="{{ url_for('generar_orden') }}" class="btn btn-sm {% if request.endpoint == 'generar_orden' %}btn-light{% else %}btn-outline-light{% endif %}">Generar orden</a>
        {% endif %}
        <span class="text-white-50 small align-self-center ms-2">{{ session.get('username') }}</span>
        <a href="{{ url_for('logout') }}" class="btn btn-sm btn-outline-light">Salir</a>
      {% endif %}
    </div>
  </div>
</nav>
<div class="container-fluid py-3">
  {% with messages = get_flashed_messages(with_categories=true) %}
    {% for cat, msg in messages %}
      <div class="alert alert-{{ cat }} alert-dismissible fade show" role="alert">
        {{ msg }}<button type="button" class="btn-close" data-bs-dismiss="alert"></button>
      </div>
    {% endfor %}
  {% endwith %}
  {% block content %}{% endblock %}
</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
{% block scripts %}{% endblock %}
</body>
</html>
```

- [ ] **Step 3: Create templates/login.html**

```html
{% extends "base.html" %}
{% block content %}
<div class="d-flex justify-content-center align-items-center" style="min-height:70vh">
  <div class="card shadow-sm" style="width:320px">
    <div class="card-body p-4">
      <h5 class="text-center mb-4">Iniciar sesión</h5>
      <form method="post">
        <div class="mb-3">
          <label class="form-label small">Sucursal / Usuario</label>
          <input type="text" name="username" class="form-control" required autofocus>
        </div>
        <div class="mb-3">
          <label class="form-label small">Contraseña</label>
          <input type="password" name="password" class="form-control" required>
        </div>
        {% if error %}
          <div class="alert alert-danger small py-2">{{ error }}</div>
        {% endif %}
        <button type="submit" class="btn w-100" style="background:#2c6e8a;color:#fff">Ingresar</button>
      </form>
    </div>
  </div>
</div>
{% endblock %}
```

---

## Task 8: Nueva solicitud template + route

**Files:**
- Create: `App Pedidos/templates/nueva_solicitud.html`
- Create: `App Pedidos/templates/confirmado.html`

- [ ] **Step 1: Create templates/nueva_solicitud.html**

```html
{% extends "base.html" %}
{% block content %}
<h5 class="mb-3">Nueva solicitud de refuerzo</h5>

{% if session.get('rol') == 'admin' %}
<div class="mb-3 d-flex align-items-center gap-2">
  <label class="form-label mb-0 small fw-bold">Crear en nombre de:</label>
  <select id="sel-sucursal" class="form-select form-select-sm" style="width:200px">
    <option value="">— Seleccioná una sucursal —</option>
    {% for s in sucursales %}
      <option value="{{ s }}">{{ s }}</option>
    {% endfor %}
  </select>
</div>
{% endif %}

<div class="filter-bar px-3">
  <div class="row g-2 align-items-end">
    <div class="col-auto">
      <label class="form-label small mb-1">Laboratorio</label>
      <input type="text" id="inp-lab" class="form-control form-control-sm" placeholder="Ej: Unilever" list="lab-list" style="width:180px">
      <datalist id="lab-list">
        {% for lab in laboratorios %}
          <option value="{{ lab }}">
        {% endfor %}
      </datalist>
    </div>
    <div class="col-auto">
      <label class="form-label small mb-1">Buscar producto</label>
      <input type="text" id="inp-q" class="form-control form-control-sm" placeholder="Nombre o EAN" style="width:220px">
    </div>
    <div class="col-auto">
      <button class="btn btn-sm text-white" style="background:#2c6e8a" onclick="buscar()">Buscar</button>
    </div>
    <div class="col-auto ms-auto">
      <button class="btn btn-sm btn-success" onclick="verSolicitud()">
        Ver solicitud (<span id="count-badge">0</span>)
      </button>
    </div>
  </div>
</div>

<div id="tabla-wrap" class="d-none">
  <table class="table table-sm table-hover">
    <thead><tr><th>EAN</th><th>Producto</th><th>Laboratorio</th><th class="text-center">Cantidad</th></tr></thead>
    <tbody id="tbody"></tbody>
  </table>
</div>

<!-- Modal revisión -->
<div class="modal fade" id="modal-revision" tabindex="-1">
  <div class="modal-dialog modal-lg">
    <div class="modal-content">
      <div class="modal-header"><h5 class="modal-title">Revisión de solicitud</h5></div>
      <div class="modal-body">
        <table class="table table-sm">
          <thead><tr><th>EAN</th><th>Producto</th><th>Laboratorio</th><th class="text-center">Cantidad</th></tr></thead>
          <tbody id="tbody-revision"></tbody>
        </table>
      </div>
      <div class="modal-footer">
        <button class="btn btn-secondary btn-sm" data-bs-dismiss="modal">← Volver a editar</button>
        <button class="btn btn-sm text-white" style="background:#5a9e6a" onclick="confirmar()">Confirmar solicitud ✓</button>
      </div>
    </div>
  </div>
</div>
{% endblock %}

{% block scripts %}
<script>
const carrito = {};
let sucursalAdmin = '';

function getSucursal() {
  const rol = '{{ session.get("rol") }}';
  if (rol === 'admin') return document.getElementById('sel-sucursal').value;
  return '{{ session.get("username") }}';
}

async function buscar() {
  const suc = getSucursal();
  if ('{{ session.get("rol") }}' === 'admin' && !suc) {
    alert('Seleccioná una sucursal primero'); return;
  }
  const lab = document.getElementById('inp-lab').value;
  const q   = document.getElementById('inp-q').value;
  if (!lab && !q) { alert('Ingresá laboratorio o nombre de producto'); return; }
  const res  = await fetch(`/api/productos?q=${encodeURIComponent(q)}&lab=${encodeURIComponent(lab)}&suc=${encodeURIComponent(suc)}`);
  const data = await res.json();
  renderTabla(data);
}

function renderTabla(prods) {
  const tbody = document.getElementById('tbody');
  tbody.innerHTML = '';
  prods.forEach(p => {
    const val = carrito[p.sku] || 0;
    tbody.innerHTML += `<tr>
      <td class="text-muted small">${p.ean}</td>
      <td>${p.descripcion}</td>
      <td>${p.laboratorio}</td>
      <td class="text-center">
        <input type="number" min="0" class="form-control form-control-sm qty-input"
          value="${val}" onchange="updateCarrito('${p.sku}','${p.ean}','${p.descripcion.replace(/'/g,"\\'")}','${p.laboratorio}','${p.drogueria}', this.value)">
      </td>
    </tr>`;
  });
  document.getElementById('tabla-wrap').classList.remove('d-none');
}

function updateCarrito(sku, ean, desc, lab, drog, val) {
  const n = parseInt(val) || 0;
  if (n > 0) carrito[sku] = {sku, ean, descripcion: desc, laboratorio: lab, drogueria: drog, cantidad: n};
  else delete carrito[sku];
  document.getElementById('count-badge').textContent = Object.keys(carrito).length;
}

function verSolicitud() {
  const items = Object.values(carrito);
  if (!items.length) { alert('No agregaste ningún producto'); return; }
  const tbody = document.getElementById('tbody-revision');
  tbody.innerHTML = items.map(it =>
    `<tr><td class="small text-muted">${it.ean}</td><td>${it.descripcion}</td><td>${it.laboratorio}</td><td class="text-center fw-bold">${it.cantidad}</td></tr>`
  ).join('');
  new bootstrap.Modal(document.getElementById('modal-revision')).show();
}

async function confirmar() {
  const suc = getSucursal();
  if (!suc) { alert('Seleccioná una sucursal'); return; }
  const items = Object.values(carrito);
  const res = await fetch('/api/solicitud', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({sucursal: suc, items})
  });
  const data = await res.json();
  if (data.numero) window.location = `/confirmado/${data.sol_id}`;
  else alert('Error al guardar: ' + (data.error || ''));
}
</script>
{% endblock %}
```

- [ ] **Step 2: Create templates/confirmado.html**

```html
{% extends "base.html" %}
{% block content %}
<div class="row justify-content-center">
  <div class="col-md-8">
    <div class="alert alert-success d-flex align-items-center gap-3 mb-4">
      <span style="font-size:2rem">✓</span>
      <div>
        <strong>Solicitud confirmada exitosamente</strong><br>
        <small>Tu pedido fue registrado y está siendo procesado por el área de compras</small>
      </div>
    </div>
    <div class="row g-3 mb-4">
      <div class="col-4">
        <div class="bg-light rounded p-3">
          <div class="small text-muted">Número de pedido</div>
          <div class="sol-number fs-5">{{ sol.numero }}</div>
        </div>
      </div>
      <div class="col-4">
        <div class="bg-light rounded p-3">
          <div class="small text-muted">Fecha de solicitud</div>
          <div class="fw-bold">{{ sol.fecha_solicitud }}</div>
        </div>
      </div>
      <div class="col-4">
        <div class="bg-light rounded p-3">
          <div class="small text-muted">Fecha de compra</div>
          <div class="text-muted fst-italic small">Pendiente de compra…</div>
        </div>
      </div>
    </div>
    <table class="table table-sm">
      <thead><tr><th>EAN</th><th>Producto</th><th>Laboratorio</th><th class="text-center">Cant.</th></tr></thead>
      <tbody>
        {% for it in items %}
        <tr>
          <td class="text-muted small">{{ it.ean }}</td>
          <td>{{ it.descripcion }}</td>
          <td>{{ it.laboratorio }}</td>
          <td class="text-center fw-bold">{{ it.cantidad }}</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
    <div class="text-end mt-3">
      <a href="{{ url_for('nueva_solicitud') }}" class="btn btn-sm btn-outline-secondary">← Nueva solicitud</a>
    </div>
  </div>
</div>
{% endblock %}
```

---

## Task 9: Mis pedidos + Consolidado + Generar orden templates

**Files:**
- Create: `App Pedidos/templates/mis_pedidos.html`
- Create: `App Pedidos/templates/consolidado.html`
- Create: `App Pedidos/templates/generar_orden.html`

- [ ] **Step 1: Create templates/mis_pedidos.html**

```html
{% extends "base.html" %}
{% block content %}
<h5 class="mb-3">
  {% if session.get('rol') == 'admin' %}Todas las solicitudes{% else %}Mis pedidos{% endif %}
</h5>
{% if session.get('rol') == 'admin' %}
<div class="filter-bar px-3 mb-3">
  <form method="get" class="row g-2 align-items-end">
    <div class="col-auto">
      <select name="suc" class="form-select form-select-sm">
        <option value="">Todas las sucursales</option>
        {% for s in sucursales %}<option value="{{ s }}" {% if filtro_suc==s %}selected{% endif %}>{{ s }}</option>{% endfor %}
      </select>
    </div>
    <div class="col-auto"><button class="btn btn-sm btn-secondary">Filtrar</button></div>
  </form>
</div>
{% endif %}
<table class="table table-sm table-hover">
  <thead><tr>
    <th>N° Pedido</th>
    {% if session.get('rol') == 'admin' %}<th>Sucursal</th>{% endif %}
    <th>Fecha solicitud</th><th>Productos</th><th>Fecha de compra</th><th class="text-center">Estado</th>
  </tr></thead>
  <tbody>
    {% for s in solicitudes %}
    <tr>
      <td><a href="{{ url_for('ver_solicitud', sol_id=s.id) }}" class="sol-number">{{ s.numero }}</a></td>
      {% if session.get('rol') == 'admin' %}<td>{{ s.sucursal }}</td>{% endif %}
      <td>{{ s.fecha_solicitud }}</td>
      <td class="text-muted">{{ s.n_items }} productos</td>
      <td>{% if s.fecha_compra %}{{ s.fecha_compra }}{% else %}<span class="text-muted fst-italic small">Pendiente…</span>{% endif %}</td>
      <td class="text-center">
        {% if s.estado == 'comprado' %}
          <span class="badge badge-comprado rounded-pill px-2">✓ Pedido realizado</span>
        {% else %}
          <span class="badge badge-pendiente rounded-pill px-2">⏳ Pendiente</span>
        {% endif %}
      </td>
    </tr>
    {% else %}
    <tr><td colspan="6" class="text-center text-muted py-4">No hay solicitudes</td></tr>
    {% endfor %}
  </tbody>
</table>
{% endblock %}
```

- [ ] **Step 2: Create templates/consolidado.html**

```html
{% extends "base.html" %}
{% block content %}
<h5 class="mb-3">Consolidado de solicitudes pendientes</h5>
<div class="filter-bar px-3 mb-3">
  <form method="get" class="row g-2 align-items-end">
    <div class="col-auto">
      <input type="text" name="lab" class="form-control form-control-sm" placeholder="Laboratorio" value="{{ filtro_lab }}" style="width:180px">
    </div>
    <div class="col-auto">
      <select name="suc" class="form-select form-select-sm" style="width:180px">
        <option value="">Todas las sucursales</option>
        {% for s in sucursales %}<option value="{{ s }}" {% if filtro_suc==s %}selected{% endif %}>{{ s }}</option>{% endfor %}
      </select>
    </div>
    <div class="col-auto">
      <select name="drog" class="form-select form-select-sm">
        <option value="">Todas las droguerías</option>
        <option value="SUD" {% if filtro_drog=='SUD' %}selected{% endif %}>SUD</option>
        <option value="SUIZO" {% if filtro_drog=='SUIZO' %}selected{% endif %}>SUIZO</option>
      </select>
    </div>
    <div class="col-auto"><button class="btn btn-sm" style="background:#2c6e8a;color:#fff">Filtrar</button></div>
    <div class="col-auto"><a href="{{ url_for('consolidado') }}" class="btn btn-sm btn-outline-secondary">Limpiar</a></div>
  </form>
</div>
<div class="row g-3 mb-3">
  <div class="col-4"><div class="bg-light rounded p-3"><div class="small text-muted">Productos</div><div class="fs-4 fw-bold">{{ productos|length }}</div></div></div>
  <div class="col-4"><div class="bg-light rounded p-3"><div class="small text-muted">Sucursales activas</div><div class="fs-4 fw-bold">{{ n_sucursales }}</div></div></div>
  <div class="col-4"><div class="bg-light rounded p-3"><div class="small text-muted">Unidades totales</div><div class="fs-4 fw-bold">{{ total_unidades }}</div></div></div>
</div>
<div class="row g-3">
  <div class="col-md-6">
    <div class="card">
      <div class="card-header small fw-bold">Productos más solicitados</div>
      <div class="card-body p-0">
        <table class="table table-sm mb-0">
          <thead><tr><th>Producto</th><th>Droguería</th><th class="text-center">Total</th></tr></thead>
          <tbody>
            {% for p in productos %}
            <tr style="cursor:pointer" onclick="verDetalle('{{ p.sku }}','{{ p.descripcion|replace("'","\\'") }}')">
              <td>{{ p.descripcion[:45] }}</td>
              <td>
                {% if p.drogueria == 'SUD' %}<span class="badge badge-sud">SUD</span>
                {% elif p.drogueria == 'SUIZO' %}<span class="badge badge-suizo">SUIZO</span>
                {% else %}<span class="text-muted small">—</span>{% endif %}
              </td>
              <td class="text-center fw-bold">{{ p.total }} u.</td>
            </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
    </div>
  </div>
  <div class="col-md-6">
    <div class="card">
      <div class="card-header small fw-bold">Detalle por sucursal — <span id="prod-titulo" class="text-muted">Hacé clic en un producto</span></div>
      <div class="card-body p-0">
        <table class="table table-sm mb-0">
          <tbody id="detalle-body"><tr><td class="text-center text-muted py-4">Seleccioná un producto</td></tr></tbody>
        </table>
      </div>
    </div>
  </div>
</div>
{% endblock %}
{% block scripts %}
<script>
async function verDetalle(sku, desc) {
  document.getElementById('prod-titulo').textContent = desc;
  const res = await fetch(`/api/detalle-sucursal?sku=${encodeURIComponent(sku)}`);
  const data = await res.json();
  const tbody = document.getElementById('detalle-body');
  if (!data.length) { tbody.innerHTML = '<tr><td class="text-center text-muted">Sin solicitudes</td></tr>'; return; }
  tbody.innerHTML = data.map(d =>
    `<tr><td><span class="chip-suc">${d.sucursal}</span></td><td class="text-muted small">${d.cantidad} unidades</td></tr>`
  ).join('');
}
</script>
{% endblock %}
```

- [ ] **Step 3: Create templates/generar_orden.html**

```html
{% extends "base.html" %}
{% block content %}
<div class="d-flex align-items-center gap-3 mb-3">
  <h5 class="mb-0">Generar orden de compra</h5>
  <span class="text-muted small">Fecha: {{ hoy }}</span>
  <div class="ms-auto d-flex gap-2">
    <a href="/exportar/SUD" class="btn btn-sm" style="background:#92400e;color:#fff">↓ Exportar SUD (.dds)</a>
    <a href="/exportar/SUIZO" class="btn btn-sm" style="background:#5b21b6;color:#fff">↓ Exportar SUIZO (.arg)</a>
  </div>
</div>
<div class="row g-3">
  {% for drog, items in orden.items() %}
  <div class="col-md-6">
    <div class="card">
      <div class="card-header d-flex justify-content-between align-items-center
        {% if drog == 'SUD' %}bg-warning bg-opacity-25{% else %}bg-purple-subtle{% endif %}">
        <span class="fw-bold {% if drog == 'SUD' %}text-warning-emphasis{% else %}text-purple{% endif %}">{{ drog }}</span>
        <span class="small text-muted">{{ items|length }} productos · {{ items|sum(attribute='cantidad') }} unidades</span>
      </div>
      <div class="card-body p-0">
        <table class="table table-sm mb-0">
          <thead><tr><th>EAN</th><th>Producto</th><th>Sucursales</th><th class="text-center">Cant.</th><th></th></tr></thead>
          <tbody>
            {% for it in items %}
            <tr>
              <td class="text-muted small">{{ it.ean[:10] }}</td>
              <td>{{ it.descripcion[:30] }}</td>
              <td>{{ it.sucursales_str }}</td>
              <td class="text-center">
                <input type="number" min="1" value="{{ it.cantidad }}"
                  class="form-control form-control-sm qty-input"
                  onchange="updateQty('{{ drog }}','{{ it.sku }}', this.value)">
              </td>
              <td>
                <button class="btn btn-sm btn-link text-danger p-0"
                  onclick="removeItem('{{ drog }}','{{ it.sku }}')">×</button>
              </td>
            </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
      <div class="card-footer">
        <button class="btn btn-sm w-100 {% if drog == 'SUD' %}btn-warning{% else %}btn-outline-secondary{% endif %}"
          onclick="marcarComprado('{{ drog }}')">
          ✓ Marcar {{ drog }} como comprado
        </button>
      </div>
    </div>
  </div>
  {% endfor %}
</div>
{% endblock %}
{% block scripts %}
<script>
async function updateQty(drog, sku, val) {
  await fetch('/api/orden/update', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({drogueria: drog, sku, cantidad: parseInt(val)})});
}
async function removeItem(drog, sku) {
  await fetch('/api/orden/remove', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({drogueria: drog, sku})});
  location.reload();
}
async function marcarComprado(drog) {
  const hoy = new Date().toLocaleDateString('es-AR');
  const res = await fetch('/api/orden/comprado', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({drogueria: drog, fecha: hoy})});
  const d = await res.json();
  if (d.ok) { alert(`Marcado como comprado. ${d.n} solicitudes actualizadas.`); location.reload(); }
}
</script>
{% endblock %}
```

---

## Task 10: Main app.py with all routes

**Files:**
- Create: `App Pedidos/app.py`

- [ ] **Step 1: Create app.py**

```python
from flask import Flask, render_template, request, session, redirect, url_for, jsonify, flash, Response
from datetime import date
from config import SECRET_KEY, SUCURSAL_NAMES, ADMIN_USER
from database import (init_db, crear_solicitud, get_solicitudes_sucursal,
                       get_solicitud_detalle, get_todas_solicitudes,
                       get_consolidado, get_detalle_por_sucursal, marcar_comprado, get_db)
from data_loader import buscar_productos, get_laboratorios, load_productos
from auth import seed_users, verify_user, login_required, admin_required
from mail_service import enviar_notificacion
from export_service import generar_suizo, generar_sud

app = Flask(__name__)
app.secret_key = SECRET_KEY

# ── Startup ────────────────────────────────────────────────────────────────
with app.app_context():
    init_db()
    seed_users()
    load_productos()   # warm cache

# ── Auth ───────────────────────────────────────────────────────────────────
@app.route('/')
def index():
    if 'username' not in session:
        return redirect(url_for('login'))
    if session.get('rol') == 'admin':
        return redirect(url_for('consolidado'))
    return redirect(url_for('nueva_solicitud'))

@app.route('/login', methods=['GET','POST'])
def login():
    error = None
    if request.method == 'POST':
        result = verify_user(request.form['username'].strip(), request.form['password'])
        if result:
            session['username'], session['rol'] = result
            return redirect(url_for('index'))
        error = 'Usuario o contraseña incorrectos'
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ── Sucursal + Admin ───────────────────────────────────────────────────────
@app.route('/nueva-solicitud')
@login_required
def nueva_solicitud():
    return render_template('nueva_solicitud.html',
        laboratorios=get_laboratorios(),
        sucursales=SUCURSAL_NAMES)

@app.route('/mis-pedidos')
@login_required
def mis_pedidos():
    suc = session['username']
    filtro_suc = request.args.get('suc','')
    if session.get('rol') == 'admin':
        solic = get_todas_solicitudes(sucursal_filtro=filtro_suc or None)
    else:
        solic = get_todas_solicitudes(sucursal_filtro=suc)
    # Add n_items count
    conn = get_db()
    for s in solic:
        row = conn.execute('SELECT COUNT(*) as c FROM items_solicitud WHERE solicitud_id=?',(s['id'],)).fetchone()
        s['n_items'] = row['c']
    conn.close()
    return render_template('mis_pedidos.html',
        solicitudes=solic, sucursales=SUCURSAL_NAMES, filtro_suc=filtro_suc)

@app.route('/confirmado/<int:sol_id>')
@login_required
def ver_solicitud(sol_id):
    sol, items = get_solicitud_detalle(sol_id)
    if not sol:
        flash('Solicitud no encontrada', 'danger')
        return redirect(url_for('mis_pedidos'))
    return render_template('confirmado.html', sol=sol, items=items)

# ── Admin only ─────────────────────────────────────────────────────────────
@app.route('/consolidado')
@login_required
@admin_required
def consolidado():
    lab  = request.args.get('lab','')
    suc  = request.args.get('suc','')
    drog = request.args.get('drog','')
    prods = get_consolidado(
        sucursal_filtro=suc or None,
        lab_filtro=lab or None,
        drogueria_filtro=drog or None
    )
    suc_set = set()
    total_u = 0
    for p in prods:
        total_u += p['total']
        for s in (p.get('sucursales') or '').split(','):
            if s.strip(): suc_set.add(s.strip())
    return render_template('consolidado.html',
        productos=prods, sucursales=SUCURSAL_NAMES,
        n_sucursales=len(suc_set), total_unidades=total_u,
        filtro_lab=lab, filtro_suc=suc, filtro_drog=drog)

@app.route('/generar-orden')
@login_required
@admin_required
def generar_orden():
    prods = get_consolidado()
    orden = {'SUD': [], 'SUIZO': [], 'SIN_PRECIO': []}
    for p in prods:
        suc_list = [s.strip() for s in (p.get('sucursales') or '').split(',') if s.strip()]
        chips = ' '.join(f'<span class="chip-suc">{s}</span>' for s in suc_list[:3])
        if len(suc_list) > 3:
            chips += f' <span class="chip-suc">+{len(suc_list)-3}</span>'
        item = {**p, 'sucursales_str': chips}
        drog = (p.get('drogueria') or '').upper()
        if drog in ('SUD','SUIZO'):
            orden[drog].append(item)
        else:
            orden['SIN_PRECIO'].append(item)
    return render_template('generar_orden.html',
        orden={k:v for k,v in orden.items() if v},
        hoy=date.today().strftime('%d/%m/%Y'))

# ── API endpoints ──────────────────────────────────────────────────────────
@app.route('/api/productos')
@login_required
def api_productos():
    q   = request.args.get('q','')
    lab = request.args.get('lab','')
    suc = request.args.get('suc','') or session.get('username','')
    results = buscar_productos(q=q, laboratorio=lab, sucursal=suc)[:200]
    return jsonify([{
        'sku': p['sku'], 'ean': p['ean'], 'descripcion': p['descripcion'],
        'laboratorio': p['laboratorio'], 'drogueria': p['drogueria'],
    } for p in results])

@app.route('/api/solicitud', methods=['POST'])
@login_required
def api_crear_solicitud():
    data = request.get_json()
    sucursal = data.get('sucursal') or session.get('username')
    items    = data.get('items', [])
    if not items:
        return jsonify({'error': 'Sin productos'}), 400
    numero, sol_id = crear_solicitud(sucursal, session['username'], items)
    enviar_notificacion(numero, sucursal, items)
    return jsonify({'numero': numero, 'sol_id': sol_id})

@app.route('/api/detalle-sucursal')
@login_required
@admin_required
def api_detalle_sucursal():
    sku = request.args.get('sku','')
    return jsonify(get_detalle_por_sucursal(sku))

@app.route('/api/orden/comprado', methods=['POST'])
@login_required
@admin_required
def api_marcar_comprado():
    data = request.get_json()
    drog = data.get('drogueria')
    fecha = data.get('fecha', date.today().strftime('%d/%m/%Y'))
    conn = get_db()
    sol_ids = [r['solicitud_id'] for r in conn.execute(
        'SELECT DISTINCT solicitud_id FROM items_solicitud WHERE drogueria=?', (drog,)
    ).fetchall()]
    conn.close()
    marcar_comprado(sol_ids, fecha)
    return jsonify({'ok': True, 'n': len(sol_ids)})

# ── Export routes ──────────────────────────────────────────────────────────
@app.route('/exportar/<drogueria>')
@login_required
@admin_required
def exportar(drogueria):
    drog = drogueria.upper()
    prods = get_consolidado(drogueria_filtro=drog)
    if not prods:
        flash(f'No hay productos para {drog}', 'warning')
        return redirect(url_for('generar_orden'))

    # Enrich with troquel for SUD
    prod_map = {p['sku']: p for p in load_productos()}
    items = []
    for p in prods:
        base = prod_map.get(p['sku'], {})
        items.append({
            'ean':         p['ean'],
            'troquel':     base.get('troquel','0000000'),
            'descripcion': p['descripcion'],
            'cantidad':    p['total'],
        })

    if drog == 'SUIZO':
        content  = generar_suizo(items)
        filename = f'pedido_suizo_{date.today().strftime("%d%m%y")}.arg'
        mimetype = 'application/octet-stream'
    else:
        content  = generar_sud(items)
        filename = f'pedido_sud_{date.today().strftime("%d%m%y")}.dds'
        mimetype = 'application/octet-stream'

    return Response(
        content,
        mimetype=mimetype,
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
```

---

## Task 11: Run and verify

- [ ] **Step 1: Run the app**

```bash
cd "C:\Users\d.dartayet\Desktop\Tio Clau\App Pedidos"
python app.py
```
Expected output:
```
 * Running on http://0.0.0.0:5000
 * Debug mode: on
```

- [ ] **Step 2: Open in browser and verify login**

Open `http://localhost:5000`. Should redirect to login page. Login with `CERRO` / `cerro123`. Should redirect to Nueva solicitud.

- [ ] **Step 3: Verify product search**

Type "unilever" in Laboratorio field, click Buscar. Should show table with AXE, DOVE, etc.

- [ ] **Step 4: Verify admin login**

Login with `admin` / `admin123`. Should show nav with Consolidado and Generar orden tabs.

- [ ] **Step 5: Configure mail (optional)**

In `config.py`, set `MAIL_USERNAME` and `MAIL_PASSWORD` (Gmail app password). If left blank, mail is skipped gracefully.

Instructions to get Gmail App Password:
1. Go to myaccount.google.com → Security → 2-Step Verification → App passwords
2. Create app password for "Mail"
3. Paste the 16-char password in `config.py`

---

## Task 12: ngrok setup for internet access

- [ ] **Step 1: Install ngrok**

Download from https://ngrok.com/download and install. Create free account and get auth token.

```bash
ngrok config add-authtoken <YOUR_TOKEN>
```

- [ ] **Step 2: Expose app**

With `python app.py` running in one terminal, open another and run:
```bash
ngrok http 5000
```
Expected: Shows a public URL like `https://abc123.ngrok-free.app`

- [ ] **Step 3: Share URL with sucursales**

Give each sucursal their username and password. They access the public ngrok URL from any browser, any location.

Note: The ngrok URL changes each time you restart ngrok. For a permanent URL, deploy to Railway (see design doc).
