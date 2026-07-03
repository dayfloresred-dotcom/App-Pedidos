# Rediseño UX/UI App-Pedidos — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Aplicar el sistema de diseño terracota refinada + micro-UX (toasts, confirmaciones, loading) + refresco por fragmento (sin `location.reload()`) según el spec `docs/superpowers/specs/2026-07-03-ux-ui-redesign-design.md`.

**Architecture:** Sistema de diseño en variables CSS sobre Bootstrap 5 (sin build step). Módulo `ui.js` global para micro-UX. La grilla de Generar orden se extrae a un partial Jinja renderizable por una ruta de fragmento; el JS reemplaza `location.reload()` por swap del fragmento preservando estado de UI. La lógica de negocio queda 100 % server-side.

**Tech Stack:** Flask 3 + Jinja2, Bootstrap 5.3 CDN, CSS vanilla con custom properties, JS vanilla, Inter vía Google Fonts, pytest para tests de backend/smoke.

## Global Constraints

- **Sin build step ni dependencias runtime nuevas.** Única adición externa: `<link>` a `fonts.googleapis.com` (Inter), con fallback `system-ui`.
- **Ningún color hex en templates.** Todo color vive en `static/style.css` como variable o clase. (Excepción transitoria: los templates aún no migrados en tareas intermedias.)
- **Los endpoints existentes (`/api/orden/*`, `/api/item/*`, exports) y su lógica NO se modifican.** Solo se agregan: ruta de fragmento de orden, ruta de fragmento de confirmado, función `_armar_orden()`, índices SQLite.
- **Se conservan los nombres de clases CSS existentes** (`badge-pendiente`, `badge-sud`, `chip-suc`, `filter-bar`, `sol-number`, `qty-input`, `env-input`, etc.): se restilan centralmente, así los templates requieren mínimos cambios estructurales.
- Copy de UI en español, sentence case, sin signos de exclamación en mensajes de sistema.
- Commits en español, estilo del repo. Cada commit con sufijo `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Rama de trabajo: `ui-redesign`. **Nada se pushea a GitHub ni se despliega al VPS sin aprobación explícita del usuario** (Task 12 requiere su OK).
- Python de trabajo local (venv ya creado): `C:/Users/e.pernochi/AppData/Local/Temp/claude/C--Users-e-pernochi-Proyectos-Claude-App-pedidos/6678761c-1269-44c8-b258-9a9874cdb57b/scratchpad/venv-pedidos/Scripts/python.exe` — abreviado abajo como `$PY`.

---

### Task 1: Infraestructura de tests (pytest + fixtures + smoke)

**Files:**
- Create: `tests/conftest.py`
- Create: `tests/test_smoke.py`

**Interfaces:**
- Produces: fixtures `client` (Flask test client sin login), `admin` (logueado como admin/admin123), `sucursal` (logueado como CERRO/cerro123). Los tests de tareas posteriores las consumen tal cual.

- [ ] **Step 1: Instalar pytest en el venv**

Run: `$PY -m pip install -q pytest`
Expected: sin errores.

- [ ] **Step 2: Crear `tests/conftest.py`**

```python
import os
import sys
import tempfile

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

_tmp = tempfile.mkdtemp(prefix='pedidos-test-')
os.environ.setdefault('PEDIDOS_DB_PATH', os.path.join(_tmp, 'test.db'))
os.environ.setdefault('PEDIDOS_DATA_DIR', os.path.join(_tmp, 'archivos'))
os.environ.setdefault('SECRET_KEY', 'clave-test')

import pytest  # noqa: E402
import app as app_module  # noqa: E402  (importa la app DESPUÉS de setear env)


@pytest.fixture()
def client():
    app_module.app.config['TESTING'] = True
    with app_module.app.test_client() as c:
        yield c


@pytest.fixture()
def admin(client):
    client.post('/login', data={'username': 'admin', 'password': 'admin123'})
    return client


@pytest.fixture()
def sucursal(client):
    client.post('/login', data={'username': 'CERRO', 'password': 'cerro123'})
    return client
```

- [ ] **Step 3: Crear `tests/test_smoke.py`**

```python
def test_health(client):
    r = client.get('/health')
    assert r.status_code == 200
    assert r.get_json()['status'] == 'ok'


def test_login_page(client):
    assert client.get('/login').status_code == 200


def test_root_redirige_a_login(client):
    r = client.get('/')
    assert r.status_code == 302
    assert '/login' in r.headers['Location']


def test_paginas_admin_renderizan(admin):
    for url in ['/consolidado', '/generar-orden', '/mis-pedidos',
                '/nueva-solicitud', '/actualizar-datos']:
        assert admin.get(url).status_code == 200, url


def test_sucursal_no_ve_admin(sucursal):
    assert sucursal.get('/consolidado').status_code == 403
```

- [ ] **Step 4: Correr los tests**

Run: `cd C:/Users/e.pernochi/Proyectos-Claude/App-pedidos && $PY -m pytest tests/ -v`
Expected: 5 PASS. (El catálogo vacío no es problema: `load_productos()` devuelve `[]` sin archivos.)

- [ ] **Step 5: Commit**

```bash
git add tests/
git commit -m "Tests: infraestructura pytest + smoke de rutas (fixtures client/admin/sucursal)"
```

---

### Task 2: Índices SQLite en init_db (TDD)

**Files:**
- Modify: `database.py:74` (final de `init_db`, antes del `conn.commit()`)
- Test: `tests/test_database.py`

**Interfaces:**
- Produces: índices `idx_items_sku`, `idx_items_solicitud`, `idx_envios_suc_sku`, `idx_omitidos_suc_sku` (los usa implícitamente el fragmento de Task 3).

- [ ] **Step 1: Test que falla**

Crear `tests/test_database.py`:

```python
import os
import sqlite3

import database


def test_init_db_crea_indices():
    database.init_db()
    conn = sqlite3.connect(os.environ['PEDIDOS_DB_PATH'])
    nombres = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index'")}
    conn.close()
    for idx in ['idx_items_sku', 'idx_items_solicitud',
                'idx_envios_suc_sku', 'idx_omitidos_suc_sku']:
        assert idx in nombres, idx
```

Run: `$PY -m pytest tests/test_database.py -v`
Expected: FAIL (`assert 'idx_items_sku' in nombres`).

- [ ] **Step 2: Implementación mínima**

En `database.py`, dentro de `init_db()`, inmediatamente antes del `conn.commit()` final agregar:

```python
    # Índices: aceleran get_consolidado / get_items_detalle / get_envios,
    # que se ejecutan por producto en cada render de Generar orden.
    conn.execute("CREATE INDEX IF NOT EXISTS idx_items_sku ON items_solicitud(sku)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_items_solicitud ON items_solicitud(solicitud_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_envios_suc_sku ON envios(sucursal, sku)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_omitidos_suc_sku ON omitidos(sucursal, sku)")
```

- [ ] **Step 3: Verificar que pasa**

Run: `$PY -m pytest tests/ -v`
Expected: todos PASS.

- [ ] **Step 4: Commit**

```bash
git add database.py tests/test_database.py
git commit -m "Perf: indices SQLite para items_solicitud/envios/omitidos (acelera Generar orden)"
```

---

### Task 3: Backend del refresco — `_armar_orden()` + ruta fragmento + partial (TDD)

**Files:**
- Modify: `app.py:119-200` (vista `generar_orden`)
- Create: `templates/_orden_grid.html`
- Modify: `templates/generar_orden.html` (extraer la grilla al partial)
- Test: `tests/test_fragmento.py`

**Interfaces:**
- Consumes: fixtures de Task 1.
- Produces: `_armar_orden(filtro_suc: str) -> tuple[dict, list]` (orden filtrada sin claves vacías, lista `sucs_orden`); ruta `GET /generar-orden/fragmento?suc=<sucursal>` (admin) que devuelve el HTML del partial; el div `id="orden-grid"` en la página completa envolviendo el `{% include %}`. Task 11 consume la ruta y el div.

- [ ] **Step 1: Tests que fallan**

Crear `tests/test_fragmento.py`:

```python
def test_fragmento_orden_admin(admin):
    r = admin.get('/generar-orden/fragmento')
    assert r.status_code == 200
    # sin datos: el partial muestra el alert de vacío
    assert b'No hay solicitudes pendientes' in r.data


def test_fragmento_orden_requiere_admin(sucursal):
    assert sucursal.get('/generar-orden/fragmento').status_code == 403


def test_pagina_orden_incluye_contenedor_grid(admin):
    r = admin.get('/generar-orden')
    assert b'id="orden-grid"' in r.data
```

Run: `$PY -m pytest tests/test_fragmento.py -v`
Expected: FAIL (404 en fragmento; falta `orden-grid`).

- [ ] **Step 2: Refactor `_armar_orden` en app.py**

Reemplazar la vista `generar_orden()` completa (líneas 119-200) por: una función privada con TODA la lógica actual, la vista de página y la vista de fragmento. La lógica interna se copia idéntica (mismo cuerpo actual desde `prods = get_consolidado(...)` hasta `sucs_orden = sorted(sucs_set)`), solo cambia el envoltorio:

```python
def _armar_orden(filtro_suc):
    """Arma la orden agrupada por droguería. Única fuente de verdad para
    la página completa y el fragmento (refresco sin reload)."""
    prods    = get_consolidado(sucursal_filtro=filtro_suc or None)
    prod_map = {p['sku']: p for p in load_productos()}
    orden    = {'DROGUERIA RED': [], 'SUD': [], 'SUIZO': [], 'SIN_PRECIO': []}

    conn = get_db()
    omit_map = {}
    for r in conn.execute("SELECT sucursal, sku, drogueria FROM omitidos").fetchall():
        omit_map.setdefault((r['sucursal'], r['sku']), set()).add(r['drogueria'])
    conn.close()

    def visibles(detalle, sku, code):
        out = []
        for d in detalle:
            env = d['enviado']
            if env.get(code):
                continue
            if env.get('ROT'):
                continue
            if code in omit_map.get((d['sucursal'], sku), set()):
                continue
            out.append(d)
        return out

    for p in prods:
        sku = p['sku']
        suc_list = [s.strip() for s in (p.get('sucursales') or '').split(',') if s.strip()]
        chips = ' '.join(f'<span class="chip-suc">{s}</span>' for s in suc_list[:3])
        if len(suc_list) > 3:
            chips += f' <span class="chip-suc">+{len(suc_list)-3}</span>'
        base     = prod_map.get(sku, {})
        raw_cd   = base.get('stock_cd', 0)
        stock_cd = raw_cd if isinstance(raw_cd, int) else (1 if raw_cd == 'SI' else 0)
        drog_ext = base.get('drog_ext', '')
        detalle = get_items_detalle(sku)
        if filtro_suc:
            detalle = [d for d in detalle if d['sucursal'] == filtro_suc]
        for d in detalle:
            d['enviado'] = get_envios(d['sucursal'], sku)
        drog = (p.get('drogueria') or '').upper()
        base_item = {**p, 'sucursales_str': chips, 'stock_cd': stock_cd, 'drog_ext': drog_ext}

        if drog == 'DROGUERIA RED':
            vis_cd = visibles(detalle, sku, 'CD')
            if vis_cd:
                orden['DROGUERIA RED'].append({**base_item, 'es_overflow': False,
                    'detalle_suc': vis_cd, 'drog_code': 'CD'})
            overflow = p['total'] - stock_cd
            if overflow > 0 and drog_ext in ('SUD', 'SUIZO'):
                vis_ext = visibles(detalle, sku, drog_ext)
                if vis_ext:
                    orden[drog_ext].append({**base_item, 'total': overflow, 'es_overflow': True,
                        'detalle_suc': vis_ext, 'drog_code': drog_ext})
        elif drog in ('SUD', 'SUIZO'):
            vis = visibles(detalle, sku, drog)
            if vis:
                orden[drog].append({**base_item, 'es_overflow': False,
                    'detalle_suc': vis, 'drog_code': drog})
        else:
            orden['SIN_PRECIO'].append({**base_item, 'es_overflow': False,
                'detalle_suc': detalle, 'drog_code': ''})

    conn = get_db()
    sucs_set = {r['sucursal'] for r in conn.execute(
        "SELECT DISTINCT sucursal FROM envios WHERE cantidad>0").fetchall()}
    conn.close()
    for its in orden.values():
        for it in its:
            for d in it['detalle_suc']:
                sucs_set.add(d['sucursal'])
    sucs_orden = sorted(sucs_set)

    return {k: v for k, v in orden.items() if v}, sucs_orden


@app.route('/generar-orden')
@login_required
@admin_required
def generar_orden():
    filtro_suc = request.args.get('suc', '')
    orden, sucs_orden = _armar_orden(filtro_suc)
    return render_template('generar_orden.html',
        orden=orden,
        sucs_orden=sucs_orden,
        sucursales=SUCURSAL_NAMES,
        filtro_suc=filtro_suc,
        hoy=now_local().strftime('%d/%m/%Y'))


@app.route('/generar-orden/fragmento')
@login_required
@admin_required
def generar_orden_fragmento():
    """Solo la grilla de tarjetas, para refrescar sin recargar la página."""
    filtro_suc = request.args.get('suc', '')
    orden, _ = _armar_orden(filtro_suc)
    return render_template('_orden_grid.html', orden=orden)
```

- [ ] **Step 3: Extraer el partial `templates/_orden_grid.html`**

Mover desde `templates/generar_orden.html` el bloque que arranca en `{% if not orden %}` (línea 30) y termina en el cierre del `<div class="row g-3">` (línea 141, el `</div>` anterior a `{% endblock %}`) a un archivo nuevo `templates/_orden_grid.html`, tal cual (sin cambios de contenido).

En `generar_orden.html`, en su lugar dejar:

```html
<div id="orden-grid">
  {% include '_orden_grid.html' %}
</div>
```

- [ ] **Step 4: Verificar tests**

Run: `$PY -m pytest tests/ -v`
Expected: todos PASS (incluidos los 3 nuevos).

- [ ] **Step 5: Commit**

```bash
git add app.py templates/_orden_grid.html templates/generar_orden.html tests/test_fragmento.py
git commit -m "Generar orden: extrae _armar_orden() + ruta /generar-orden/fragmento + partial de grilla"
```

---

### Task 4: Sistema de diseño — `static/style.css` completo

**Files:**
- Modify: `static/style.css` (reemplazo total del contenido)

**Interfaces:**
- Produces: variables `--brand`, `--fondo`, etc. y clases `.btn-brand`, `.btn-suave`, `.btn-peligro`, `.badge-estado`, `.badge-generado`, `.badge-rot`, `.badge-cd`, `.tarjeta-head-drog`, `.toast-app`, `.metric-card`, `.pill-suc`, `.card-scroll` + restyle de las clases existentes (`badge-pendiente`, `badge-comprado`, `badge-cancelado`, `badge-sud`, `badge-suizo`, `chip-suc`, `sol-number`, `filter-bar`, `qty-input`, `env-input`). Tasks 5-11 consumen estas clases.

- [ ] **Step 1: Reemplazar `static/style.css` por el sistema completo**

```css
/* ============================================================
   App-Pedidos — Sistema de diseño (terracota refinada)
   Todo el color del portal vive acá. Cero hex en templates.
   ============================================================ */
:root {
  --brand: #8E4F44;
  --brand-hover: #74392F;
  --brand-tint: #F3E3DE;
  --fondo: #F6F1EA;
  --tarjeta: #FFFFFF;
  --tarjeta-head: #FBF8F3;
  --borde: #E8DFD3;
  --texto: #2B2622;
  --texto-sec: #6E655B;
  --texto-suave: #8A7E72;
  --ok-bg: #E3F1E7;      --ok-tx: #20603B;
  --warn-bg: #FCF3D9;    --warn-tx: #8A6116;
  --peligro: #A3372B;    --peligro-bg: #FBE9E6;
  --gen-bg: #FDF0E4;     --gen-tx: #9A4E12;
  --cd-bg: #E3F1E7;      --cd-tx: #1D6B3E;
  --sud-bg: #F8EBD4;     --sud-tx: #8A5A12;
  --suizo-bg: #EFEAFB;   --suizo-tx: #5B34B5;
  --rot-bg: #E4F0F6;     --rot-tx: #155E75;
  --radio: 10px;
}

/* ---------- Base ---------- */
body {
  background: var(--fondo);
  color: var(--texto);
  font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif;
  font-size: 14px;
}
h5 { font-weight: 600; color: var(--texto); }

/* ---------- Navbar ---------- */
.navbar-app { background: var(--brand); padding: .55rem 1rem; }
.navbar-app .navbar-brand { color: #fff; font-weight: 600; font-size: 15px; display: flex; align-items: center; gap: 8px; }
.brand-circle {
  width: 26px; height: 26px; border-radius: 50%;
  background: #fff; color: var(--brand);
  font-size: 11px; font-weight: 700;
  display: inline-flex; align-items: center; justify-content: center;
}
.brand-sub { opacity: .65; font-weight: 400; }
.nav-btn {
  color: #F3DAD3 !important; background: transparent; border: 0;
  font-size: 13px; padding: .35rem .9rem; border-radius: 99px;
}
.nav-btn:hover { color: #fff !important; background: rgba(255,255,255,.12); }
.nav-btn.active { color: #fff !important; background: rgba(255,255,255,.18); }
.user-chip {
  width: 28px; height: 28px; border-radius: 50%;
  background: rgba(255,255,255,.22); color: #fff;
  font-size: 10px; font-weight: 600;
  display: inline-flex; align-items: center; justify-content: center;
}
.navbar-app .navbar-toggler { border-color: rgba(255,255,255,.4); }
.navbar-app .navbar-toggler-icon { filter: invert(1); }

/* ---------- Tarjetas y tablas ---------- */
.card { border: 1px solid var(--borde); border-radius: var(--radio); background: var(--tarjeta); }
.card-header { background: var(--tarjeta-head); border-bottom: 1px solid var(--borde); font-weight: 600; }
.card-footer { background: var(--tarjeta-head); border-top: 1px solid var(--borde); }
.card-scroll { max-height: 480px; overflow-y: auto; }
.table { color: var(--texto); }
.table thead th {
  background: var(--tarjeta-head); color: var(--texto-suave);
  font-size: 10.5px; font-weight: 600; text-transform: uppercase;
  letter-spacing: .4px; border-bottom: 1px solid var(--borde);
  position: sticky; top: 0; z-index: 1;
}
.table td { border-color: #F0EAE0; vertical-align: middle; }
.table-hover tbody tr:hover { background: #FBF8F3; }
.fila-activa { background: var(--brand-tint) !important; }

/* Tabla suelta (fuera de .card): la envolvemos en tarjeta */
.tabla-card { background: var(--tarjeta); border: 1px solid var(--borde); border-radius: var(--radio); overflow: hidden; }
.tabla-card .table { margin-bottom: 0; }

/* ---------- Botones ---------- */
.btn-brand { background: var(--brand); color: #fff; border: 0; }
.btn-brand:hover, .btn-brand:focus { background: var(--brand-hover); color: #fff; }
.btn-suave { background: var(--tarjeta); color: var(--texto-sec); border: 1px solid var(--borde); }
.btn-suave:hover { background: var(--tarjeta-head); color: var(--texto); }
.btn-peligro { background: var(--peligro); color: #fff; border: 0; }
.btn-peligro:hover { background: #86281E; color: #fff; }

/* ---------- Badges de estado ---------- */
.badge-pendiente, .badge-comprado, .badge-cancelado, .badge-generado,
.badge-estado {
  font-size: 11px; font-weight: 600; padding: 3px 10px; border-radius: 99px;
  display: inline-block; white-space: nowrap;
}
.badge-pendiente { background: var(--warn-bg); color: var(--warn-tx); }
.badge-comprado  { background: var(--ok-bg);   color: var(--ok-tx); }
.badge-cancelado { background: var(--peligro-bg); color: var(--peligro); }
.badge-generado  { background: var(--gen-bg);  color: var(--gen-tx); }

/* ---------- Badges de droguería / origen ---------- */
.badge-cd, .badge-sud, .badge-suizo, .badge-rot {
  font-size: 10px; font-weight: 600; padding: 2px 9px; border-radius: 99px;
  display: inline-block; white-space: nowrap;
}
.badge-cd    { background: var(--cd-bg);    color: var(--cd-tx); }
.badge-sud   { background: var(--sud-bg);   color: var(--sud-tx); }
.badge-suizo { background: var(--suizo-bg); color: var(--suizo-tx); }
.badge-rot   { background: var(--rot-bg);   color: var(--rot-tx); }

/* Cabeceras de tarjeta por droguería (Generar orden) */
.head-cd    { background: var(--cd-bg) !important; }    .head-cd .drog-nombre { color: var(--cd-tx); }
.head-sud   { background: var(--sud-bg) !important; }   .head-sud .drog-nombre { color: var(--sud-tx); }
.head-suizo { background: var(--suizo-bg) !important; } .head-suizo .drog-nombre { color: var(--suizo-tx); }
.head-sinprecio { background: var(--peligro-bg) !important; } .head-sinprecio .drog-nombre { color: var(--peligro); }
.drog-nombre { font-weight: 700; }

/* ---------- Chips y misc ---------- */
.chip-suc {
  background: var(--brand-tint); color: var(--brand-hover);
  font-size: 10px; font-weight: 600; padding: 2px 8px; border-radius: 99px;
  display: inline-block; margin: 1px;
}
.sol-number { color: var(--brand); font-weight: 600; text-decoration: none; }
.sol-number:hover { color: var(--brand-hover); text-decoration: underline; }
.filter-bar {
  background: var(--tarjeta); border: 1px solid var(--borde);
  border-radius: var(--radio); padding: .75rem 1rem; margin-bottom: 1rem;
}
.excedente-tag { background: var(--rot-bg); color: var(--rot-tx); font-size: 10px; padding: 1px 6px; border-radius: 8px; }

/* Pills de detalle por sucursal (Generar orden) */
.pill-suc {
  background: var(--tarjeta); border: 1px solid var(--borde);
  border-radius: 8px; padding: .35rem .6rem;
  display: flex; align-items: center; gap: .5rem;
}
.detalle-row-bg { background: var(--tarjeta-head); }

/* ---------- Formularios ---------- */
.form-control, .form-select { border-color: var(--borde); color: var(--texto); }
.form-control:focus, .form-select:focus {
  border-color: var(--brand); box-shadow: 0 0 0 .2rem rgba(142, 79, 68, .15);
}
.qty-input, .env-input { min-height: 34px; }
@media (pointer: coarse) { .qty-input, .env-input { min-height: 42px; } }

/* ---------- Metric cards (confirmado / consolidado) ---------- */
.metric-card {
  background: var(--tarjeta-head); border: 1px solid var(--borde);
  border-radius: var(--radio); padding: .9rem 1rem;
}
.metric-card .metric-label { font-size: 12px; color: var(--texto-suave); }
.metric-card .metric-valor { font-size: 20px; font-weight: 600; }

/* ---------- Toasts ---------- */
#toast-wrap {
  position: fixed; right: 16px; bottom: 16px; z-index: 2000;
  display: flex; flex-direction: column; gap: 8px; align-items: flex-end;
}
.toast-app {
  background: var(--texto); color: #fff; font-size: 13px;
  padding: .6rem .9rem; border-radius: 8px;
  display: flex; align-items: center; gap: 8px;
  opacity: 0; transform: translateY(8px);
  transition: opacity .25s ease, transform .25s ease;
  max-width: 360px;
}
.toast-app.show { opacity: 1; transform: none; }
.toast-app .toast-ic { font-weight: 700; }
.toast-exito .toast-ic { color: #7BC495; }
.toast-error .toast-ic { color: #F09A8D; }
.toast-info  .toast-ic { color: #9CC4DB; }

/* ---------- Modal de confirmación ---------- */
.conf-titulo { font-weight: 600; margin-bottom: .35rem; }
.conf-msg { color: var(--texto-sec); font-size: 13.5px; }

/* ---------- Login ---------- */
.login-wrap { min-height: 100vh; display: flex; align-items: center; justify-content: center; }
.login-card { width: 100%; max-width: 380px; padding: 2rem; }
.login-brand { display: flex; flex-direction: column; align-items: center; gap: .5rem; margin-bottom: 1.25rem; }
.login-brand .brand-circle { width: 44px; height: 44px; font-size: 16px; background: var(--brand); color: #fff; }

/* ---------- Responsive ---------- */
@media (max-width: 575.98px) {
  .tabla-card, .card-scroll { overflow-x: auto; }
  .table { min-width: 560px; }
  .filter-bar .row > .col-auto { width: 100%; }
  .filter-bar .form-control, .filter-bar .form-select { width: 100% !important; }
  .botonera-movil { display: flex; flex-direction: column; gap: .5rem; align-items: stretch !important; }
}
```

- [ ] **Step 2: Smoke + verificación visual mínima**

Run: `$PY -m pytest tests/ -v`
Expected: todos PASS (el CSS no rompe rutas).
Además: levantar local `PEDIDOS_DB_PATH=... $PY app.py` NO es necesario aún — la verificación visual completa es en Task 11/12; acá basta pytest.

- [ ] **Step 3: Commit**

```bash
git add static/style.css
git commit -m "UI: sistema de diseno completo en style.css (tokens terracota + componentes)"
```

---

### Task 5: Módulo `static/ui.js` + `templates/base.html` rediseñada

**Files:**
- Create: `static/ui.js`
- Modify: `templates/base.html` (reemplazo total)

**Interfaces:**
- Produces (globales JS, las consumen Tasks 7-11): `toast(mensaje, tipo)` con `tipo ∈ {'exito','error','info'}`; `confirmar(mensaje, opts) -> Promise<boolean>` con `opts = {titulo?, accion?, peligro?}` (default peligro=true → botón rojo); `setLoading(boton, estado)`.

- [ ] **Step 1: Crear `static/ui.js`**

```javascript
/* Micro-UX global: toasts, confirmaciones y estados de carga.
   Requiere bootstrap.bundle (ya cargado en base.html). */
(function () {
  function contenedor() {
    let c = document.getElementById('toast-wrap');
    if (!c) {
      c = document.createElement('div');
      c.id = 'toast-wrap';
      document.body.appendChild(c);
    }
    return c;
  }

  window.toast = function (mensaje, tipo) {
    tipo = tipo || 'info';
    const el = document.createElement('div');
    el.className = 'toast-app toast-' + tipo;
    const ic = tipo === 'exito' ? '✓' : (tipo === 'error' ? '✕' : 'ℹ');
    const icon = document.createElement('span');
    icon.className = 'toast-ic';
    icon.textContent = ic;
    const txt = document.createElement('span');
    txt.textContent = mensaje;
    el.appendChild(icon); el.appendChild(txt);
    contenedor().appendChild(el);
    requestAnimationFrame(() => el.classList.add('show'));
    setTimeout(() => {
      el.classList.remove('show');
      setTimeout(() => el.remove(), 300);
    }, 3500);
  };

  window.confirmar = function (mensaje, opts) {
    opts = opts || {};
    return new Promise((resolve) => {
      const viejo = document.getElementById('modal-confirmar-app');
      if (viejo) viejo.remove();
      const div = document.createElement('div');
      div.id = 'modal-confirmar-app';
      div.innerHTML =
        '<div class="modal fade" tabindex="-1">' +
        '  <div class="modal-dialog modal-dialog-centered">' +
        '    <div class="modal-content">' +
        '      <div class="modal-body">' +
        '        <div class="conf-titulo"></div>' +
        '        <div class="conf-msg"></div>' +
        '      </div>' +
        '      <div class="modal-footer border-0 pt-0">' +
        '        <button type="button" class="btn btn-suave btn-sm" data-bs-dismiss="modal">Volver</button>' +
        '        <button type="button" class="btn btn-sm conf-ok"></button>' +
        '      </div>' +
        '    </div>' +
        '  </div>' +
        '</div>';
      document.body.appendChild(div);
      const modalEl = div.querySelector('.modal');
      modalEl.querySelector('.conf-titulo').textContent = opts.titulo || 'Confirmar acción';
      modalEl.querySelector('.conf-msg').textContent = mensaje;
      const ok = modalEl.querySelector('.conf-ok');
      ok.textContent = opts.accion || 'Confirmar';
      ok.classList.add(opts.peligro === false ? 'btn-brand' : 'btn-peligro');
      let confirmado = false;
      const m = new bootstrap.Modal(modalEl);
      ok.addEventListener('click', () => { confirmado = true; m.hide(); });
      modalEl.addEventListener('hidden.bs.modal', () => { div.remove(); resolve(confirmado); });
      m.show();
    });
  };

  window.setLoading = function (btn, estado) {
    if (!btn) return;
    if (estado) {
      btn.dataset.htmlOriginal = btn.innerHTML;
      btn.disabled = true;
      btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status"></span>' +
        btn.textContent.trim();
    } else {
      btn.disabled = false;
      if (btn.dataset.htmlOriginal) btn.innerHTML = btn.dataset.htmlOriginal;
    }
  };
})();
```

- [ ] **Step 2: Reemplazar `templates/base.html` completo**

```html
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Farmacias Red — Pedidos</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">
</head>
<body>
<nav class="navbar navbar-expand-lg navbar-app">
  <div class="container-fluid">
    <span class="navbar-brand">
      <span class="brand-circle">FR</span>
      Farmacias Red <span class="brand-sub">Pedidos</span>
    </span>
    {% if session.get('username') %}
    <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#nav-principal"
            aria-controls="nav-principal" aria-expanded="false" aria-label="Menú">
      <span class="navbar-toggler-icon"></span>
    </button>
    <div class="collapse navbar-collapse" id="nav-principal">
      <div class="d-flex gap-1 flex-wrap align-items-center ms-lg-3 mt-2 mt-lg-0">
        <a href="{{ url_for('nueva_solicitud') }}" class="btn btn-sm nav-btn {% if request.endpoint == 'nueva_solicitud' %}active{% endif %}">Nueva solicitud</a>
        <a href="{{ url_for('mis_pedidos') }}" class="btn btn-sm nav-btn {% if request.endpoint == 'mis_pedidos' %}active{% endif %}">Mis pedidos</a>
        {% if session.get('rol') == 'admin' %}
          <a href="{{ url_for('consolidado') }}" class="btn btn-sm nav-btn {% if request.endpoint == 'consolidado' %}active{% endif %}">Consolidado</a>
          <a href="{{ url_for('generar_orden') }}" class="btn btn-sm nav-btn {% if request.endpoint == 'generar_orden' %}active{% endif %}">Generar orden</a>
          <a href="{{ url_for('actualizar_datos') }}" class="btn btn-sm nav-btn {% if request.endpoint == 'actualizar_datos' %}active{% endif %}">Actualizar datos</a>
        {% endif %}
      </div>
      <div class="d-flex gap-2 align-items-center ms-lg-auto mt-2 mt-lg-0">
        <span class="user-chip" title="{{ session.get('username') }}">{{ session.get('username')[:2] }}</span>
        <a href="{{ url_for('logout') }}" class="btn btn-sm nav-btn">Salir</a>
      </div>
    </div>
    {% endif %}
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
<div id="toast-wrap"></div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
<script src="{{ url_for('static', filename='ui.js') }}"></script>
{% block scripts %}{% endblock %}
</body>
</html>
```

Notar: desaparece el `<style>` inline (el negro de `.nav-btn` y el fondo `#D3C4B4`), y `{{ session.get('username')[:2] }}` da las iniciales del chip.

- [ ] **Step 3: Smoke con assert de includes**

Agregar a `tests/test_smoke.py`:

```python
def test_base_incluye_sistema(admin):
    r = admin.get('/mis-pedidos')
    assert b'ui.js' in r.data
    assert b'fonts.googleapis.com' in r.data
    assert b'navbar-app' in r.data
```

Run: `$PY -m pytest tests/ -v`
Expected: todos PASS.

- [ ] **Step 4: Commit**

```bash
git add static/ui.js templates/base.html tests/test_smoke.py
git commit -m "UI: base.html rediseñada (navbar FR, Inter, colapsable) + modulo ui.js (toast/confirmar/setLoading)"
```

---

### Task 6: `templates/login.html`

**Files:**
- Modify: `templates/login.html` (reemplazo total)

- [ ] **Step 1: Reemplazar el contenido**

```html
{% extends "base.html" %}
{% block content %}
<div class="login-wrap">
  <div class="card login-card">
    <div class="login-brand">
      <span class="brand-circle">FR</span>
      <div class="fw-bold">Farmacias Red</div>
      <div class="text-muted small">Portal de pedidos de refuerzo</div>
    </div>
    {% if error %}<div class="alert alert-danger py-2 small">{{ error }}</div>{% endif %}
    <form method="post">
      <div class="mb-3">
        <label class="form-label small fw-bold">Sucursal / usuario</label>
        <input type="text" name="username" class="form-control" required autofocus>
      </div>
      <div class="mb-3">
        <label class="form-label small fw-bold">Contraseña</label>
        <input type="password" name="password" class="form-control" required>
      </div>
      <button type="submit" class="btn btn-brand w-100">Ingresar</button>
    </form>
  </div>
</div>
{% endblock %}
```

Nota: el login renderiza dentro de base.html; como no hay sesión, la navbar solo muestra la marca — correcto.

- [ ] **Step 2: Verificar** — Run: `$PY -m pytest tests/ -v` → PASS. El texto del error de login ("Usuario o contraseña incorrectos") no cambia.

- [ ] **Step 3: Commit**

```bash
git add templates/login.html
git commit -m "UI: login como tarjeta centrada con marca FR"
```

---

### Task 7: `templates/nueva_solicitud.html` — restyle + micro-UX

**Files:**
- Modify: `templates/nueva_solicitud.html`

- [ ] **Step 1: Aplicar estos reemplazos exactos**

1. Botón Buscar (línea 33): `<button class="btn btn-sm text-white" style="background:#111" onclick="buscar()">Buscar</button>` → `<button class="btn btn-sm btn-brand" onclick="buscar()">Buscar</button>`
2. Botón Ver solicitud (línea 36): `class="btn btn-sm btn-success"` → `class="btn btn-sm btn-brand"`
3. Envolver la tabla de resultados en tarjeta — reemplazar `<div id="tabla-wrap" class="d-none">` + `<table class="table table-sm table-hover">` por:

```html
<div id="tabla-wrap" class="d-none">
  <div class="tabla-card">
  <table class="table table-sm table-hover">
```

y cerrar el `</div>` extra después de `</table>` (antes del `<p class="text-muted small"...>`).

4. Color del Stock CD (línea 108, JS): `style="font-weight:600;color:${p.stock_cd==='SI'?'#166534':'#991b1b'}"` → `class="${p.stock_cd==='SI' ? 'badge-cd' : 'badge-cancelado'}"` (dentro del `<td class="text-center">` envolver el valor: `<span class="${...}">${p.stock_cd ?? 'NO'}</span>`).
5. Botón Confirmar del modal (línea 67): `class="btn btn-sm text-white" style="background:#5a9e6a"` → `class="btn btn-sm btn-brand"`.
6. Reemplazos de `alert()` en el `<script>`:
   - `alert('Seleccioná una sucursal primero')` → `toast('Seleccioná una sucursal primero', 'error')`
   - `alert('Ingresá laboratorio o nombre de producto')` → `toast('Ingresá laboratorio o nombre de producto', 'info')`
   - `alert('No agregaste ningún producto')` → `toast('No agregaste ningún producto', 'info')`
   - `alert('Seleccioná una sucursal')` → `toast('Seleccioná una sucursal', 'error')`
   - `alert('Error al guardar: ' + ...)` → `toast('Error al guardar: ' + (data.error || 'desconocido'), 'error')`
7. Loading en confirmar — la función `confirmar()` del template colisiona con el global `window.confirmar` de ui.js: **renombrarla a `confirmarSolicitud()`** (y su `onclick` en el botón del modal). Nueva versión:

```javascript
async function confirmarSolicitud(btn) {
  const suc = getSucursal();
  if (!suc) { toast('Seleccioná una sucursal', 'error'); return; }
  const items = Object.values(carrito);
  setLoading(btn, true);
  try {
    const res = await fetch('/api/solicitud', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({sucursal: suc, items})
    });
    const data = await res.json();
    if (data.sol_id) { window.location = `/confirmado/${data.sol_id}`; return; }
    toast('Error al guardar: ' + (data.error || 'desconocido'), 'error');
  } catch (e) {
    toast('Error de conexión', 'error');
  }
  setLoading(btn, false);
}
```

y el botón del modal: `onclick="confirmarSolicitud(this)"`.

- [ ] **Step 2: Verificar** — Run: `$PY -m pytest tests/ -v` → PASS. Grep de control: `grep -n "alert(" templates/nueva_solicitud.html` → sin resultados; `grep -n "#1" templates/nueva_solicitud.html` → sin hex.

- [ ] **Step 3: Commit**

```bash
git add templates/nueva_solicitud.html
git commit -m "UI: nueva solicitud con sistema de diseno + toasts + loading (sin alert)"
```

---

### Task 8: `templates/mis_pedidos.html` + `templates/actualizar_datos.html`

**Files:**
- Modify: `templates/mis_pedidos.html`
- Modify: `templates/actualizar_datos.html`

- [ ] **Step 1: mis_pedidos.html**

1. Envolver la tabla en `.tabla-card` (mismo patrón que Task 7 paso 3: `<div class="tabla-card">` antes de `<table class="table table-sm table-hover">` y `</div>` tras `</table>`).
2. Badges: quitar los emojis de los spans de estado (quedan `Pedido realizado`, `Cancelado`, `Pendiente` — las clases `badge-comprado/cancelado/pendiente` ya traen el color del sistema).
3. Botón Filtrar: `class="btn btn-sm btn-secondary"` → `class="btn btn-sm btn-brand"`.

- [ ] **Step 2: actualizar_datos.html**

Envolver cada bloque de archivo en `.metric-card` si el template usa filas sueltas; si ya usa `.card`, solo verificar que no queden estilos inline con hex (grep) y reemplazar botones `style="background:#..."` por `btn-brand`/`btn-suave`. (El template tiene 52 líneas: revisarlo entero y aplicar el criterio; el submit principal pasa a `btn-brand`.)

- [ ] **Step 3: Verificar** — Run: `$PY -m pytest tests/ -v` → PASS. `grep -nE "#[0-9a-fA-F]{3,6}" templates/mis_pedidos.html templates/actualizar_datos.html` → sin hex.

- [ ] **Step 4: Commit**

```bash
git add templates/mis_pedidos.html templates/actualizar_datos.html
git commit -m "UI: mis pedidos y actualizar datos al sistema de diseno"
```

---

### Task 9: `templates/confirmado.html` — restyle + confirmaciones + fragmento de ítems

**Files:**
- Modify: `templates/confirmado.html`
- Create: `templates/_confirmado_items.html`
- Modify: `app.py` (ruta de fragmento de confirmado, después de `ver_solicitud`)
- Test: `tests/test_fragmento.py` (agregar casos)

**Interfaces:**
- Produces: ruta `GET /confirmado/<int:sol_id>/fragmento` (login requerido, mismo permiso que ver la solicitud) que renderiza `_confirmado_items.html` (la tabla de ítems). El JS del template la consume.

- [ ] **Step 1: Tests que fallan** — agregar a `tests/test_fragmento.py`:

```python
def test_fragmento_confirmado_404_si_no_existe(admin):
    assert admin.get('/confirmado/99999/fragmento').status_code == 404
```

Run: `$PY -m pytest tests/test_fragmento.py -v` → FAIL (404 esperado pero la ruta no existe → hoy da 404 de Flask... verificar que falle por routing: usar assert del contenido). Ajuste: el test correcto es crear una solicitud vía `/api/solicitud` como sucursal y pedir su fragmento:

```python
def test_fragmento_confirmado(sucursal):
    r = sucursal.post('/api/solicitud', json={'items': [
        {'sku': 'T1', 'ean': '779', 'descripcion': 'Prueba', 'laboratorio': 'Lab', 'cantidad': 2}
    ]})
    sol_id = r.get_json()['sol_id']
    f = sucursal.get(f'/confirmado/{sol_id}/fragmento')
    assert f.status_code == 200
    assert b'Prueba' in f.data
```

Expected: FAIL con 404.

- [ ] **Step 2: Ruta en app.py** (debajo de `ver_solicitud`):

```python
@app.route('/confirmado/<int:sol_id>/fragmento')
@login_required
def ver_solicitud_fragmento(sol_id):
    sol, items = get_solicitud_detalle(sol_id)
    if not sol:
        return 'No encontrada', 404
    if session.get('rol') != 'admin' and sol['sucursal'] != session.get('username'):
        return 'Sin permiso', 403
    envios = get_envios_sucursal(sol['sucursal'])
    return render_template('_confirmado_items.html', sol=sol, items=items, envios=envios)
```

- [ ] **Step 3: Extraer `templates/_confirmado_items.html`**

Mover la `<table class="table table-sm">...</table>` de ítems (líneas 34-90 de confirmado.html) al partial, tal cual. En confirmado.html dejar en su lugar:

```html
<div class="tabla-card" id="items-wrap">
  {% include '_confirmado_items.html' %}
</div>
```

- [ ] **Step 4: Restyle + JS de confirmado.html**

1. Las 3 tarjetas de resumen (`bg-light rounded p-3`) → `metric-card` con `metric-label`/`metric-valor`.
2. Badges inline con hex (estados y "Llega desde") → clases: `badge-cancelado`, `badge-comprado`, `badge-generado`, `badge-pendiente`, `badge-cd/sud/suizo/rot` según ORIGEN (mapear en el partial: CD→`badge-cd`, SUD→`badge-sud`, SUIZO→`badge-suizo`, ROT→`badge-rot`, INEXISTENTE→`badge-cancelado`).
3. JS: reemplazar las funciones por versión con `confirmar()` + fragmento:

```javascript
async function cancelarItem(itemId) {
  const ok = await confirmar('El producto vuelve a poder restaurarse después.',
    {titulo: '¿Cancelar este producto?', accion: 'Cancelar producto'});
  if (!ok) return;
  const res = await fetch('/api/item/cancelar', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({item_id: itemId})
  });
  const d = await res.json().catch(() => ({}));
  if (res.ok && d.ok) { toast('Producto cancelado', 'exito'); refrescarItems(); }
  else toast(d.error || 'No se pudo cancelar', 'error');
}

async function restaurarItem(itemId) {
  const res = await fetch('/api/item/restaurar', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({item_id: itemId})
  });
  const d = await res.json().catch(() => ({}));
  if (res.ok && d.ok) { toast('Producto restaurado', 'exito'); refrescarItems(); }
  else toast(d.error || 'No se pudo restaurar', 'error');
}

async function refrescarItems() {
  const res = await fetch(location.pathname + '/fragmento');
  if (!res.ok) { location.reload(); return; }
  document.getElementById('items-wrap').innerHTML = await res.text();
}
```

Nota: el form de "Cancelar pedido completo" (POST clásico con redirect) se mantiene, solo su `onsubmit confirm(...)` queda como está (submit síncrono de formulario: el confirm nativo es aceptable ahí; convertirlo requeriría interceptar el submit — hacerlo: `onsubmit` → `return false` + handler con `confirmar()` es opcional, NO requerido).

- [ ] **Step 5: Verificar** — Run: `$PY -m pytest tests/ -v` → PASS (incluido `test_fragmento_confirmado`).

- [ ] **Step 6: Commit**

```bash
git add app.py templates/confirmado.html templates/_confirmado_items.html tests/test_fragmento.py
git commit -m "UI: confirmado con metric-cards, badges del sistema y refresco de items por fragmento"
```

---

### Task 10: `templates/consolidado.html`

**Files:**
- Modify: `templates/consolidado.html`

- [ ] **Step 1: Reemplazos**

1. Métricas (`bg-light rounded p-3`) → `metric-card` (label → `metric-label`, número → `metric-valor`).
2. Botón Filtrar `style="background:#111"` → `btn-brand`.
3. Badges de droguería inline (línea 46: `style="background:#dcfce7;..."`) → `<span class="badge-cd">CD</span>` (SUD/SUIZO ya usan `badge-sud`/`badge-suizo`).
4. Al hacer clic en una fila, resaltarla: en `verDetalle`, primera línea agregar:

```javascript
document.querySelectorAll('tr.fila-activa').forEach(t => t.classList.remove('fila-activa'));
event.currentTarget.classList.add('fila-activa');
```

(y en el `onclick` de la fila pasar el evento: `onclick="verDetalle(event, '{{ p.sku }}', ...)"` con la firma `async function verDetalle(event, sku, desc)`).

- [ ] **Step 2: Verificar** — Run: `$PY -m pytest tests/ -v` → PASS; grep sin hex en el template.

- [ ] **Step 3: Commit**

```bash
git add templates/consolidado.html
git commit -m "UI: consolidado con metric-cards, badges del sistema y fila activa"
```

---

### Task 11: Generar orden — restyle del partial + JS sin `location.reload()`

**Files:**
- Modify: `templates/_orden_grid.html`
- Modify: `templates/generar_orden.html` (header + `{% block scripts %}` completo)

**Interfaces:**
- Consumes: ruta `/generar-orden/fragmento` (Task 3), `toast/confirmar/setLoading` (Task 5), clases CSS (Task 4).

- [ ] **Step 1: Restyle de `_orden_grid.html`**

1. Cabecera de tarjeta: reemplazar el `style="background:{% if drog == 'SUD' %}#fef9ec{% ... %}"` y el `span` de color por:

```html
<div class="card-header d-flex justify-content-between align-items-center head-{{ 'sud' if drog == 'SUD' else 'suizo' if drog == 'SUIZO' else 'cd' if drog == 'DROGUERIA RED' else 'sinprecio' }}">
  <span class="drog-nombre">{{ drog }}</span>
  <span class="small text-muted">{{ items|length }} productos · {{ items|sum(attribute='total') }} u.</span>
</div>
```

2. `<div class="card-body p-0" style="max-height:480px;overflow-y:auto">` → `<div class="card-body p-0 card-scroll">`.
3. Tag excedente (línea 62): `<span class="ms-1" style="background:#e0f2fe;...">excedente CD</span>` → `<span class="ms-1 excedente-tag">excedente CD</span>`.
4. Badge alt. droguería (línea 70): ya usa `badge-sud`/`badge-suizo` — sin cambio.
5. Fila de detalle: `style="background:#f6fbf8"` → `class="detalle-row-bg"`; los pills `style="background:#fff"` con borde → `class="pill-suc"` (quitar las clases sueltas `border rounded px-2 py-1` que quedan cubiertas).
6. Botón del footer: reemplazar los dos `style="background:..."` por `btn-peligro` (SIN_PRECIO) y `btn-brand` (resto). El color por droguería del footer se unifica en `btn-brand` (decisión de diseño: el CTA no necesita repetir el color de la cabecera).

- [ ] **Step 2: Header de `generar_orden.html`**

Botones de export (líneas 20-27): reemplazar los 4 `class="btn btn-sm text-white" style="background:#..."` por `class="btn btn-sm btn-suave"` y el de Rotación igual. (Decisión: los exports son acciones secundarias; el color por droguería vive en las tarjetas.)

- [ ] **Step 3: Reemplazar el `{% block scripts %}` completo de `generar_orden.html`**

```html
{% block scripts %}
<script>
function toggleDet(rid, btn) {
  const row = document.querySelector('.detalle-' + CSS.escape(rid));
  if (!row) return;
  const show = row.style.display === 'none';
  row.style.display = show ? '' : 'none';
  if (btn) btn.textContent = show ? '▾' : '▸';
}

function filtroActual() {
  return new URLSearchParams(location.search).get('suc') || '';
}

async function refrescarOrden() {
  const grid = document.getElementById('orden-grid');
  const abiertos = [...grid.querySelectorAll('tr[class*="detalle-"]')]
    .filter(r => r.style.display !== 'none')
    .map(r => [...r.classList].find(c => c.startsWith('detalle-')));
  const scrolls = [...grid.querySelectorAll('.card-scroll')].map(b => b.scrollTop);
  const scrollY = window.scrollY;

  const res = await fetch('/generar-orden/fragmento?suc=' + encodeURIComponent(filtroActual()));
  if (!res.ok) { toast('No se pudo refrescar la orden', 'error'); return; }
  grid.innerHTML = await res.text();

  abiertos.forEach(cl => {
    const row = grid.querySelector('.' + CSS.escape(cl));
    if (!row) return;
    row.style.display = '';
    const rid = cl.replace('detalle-', '');
    const btn = grid.querySelector(`button[onclick*="${rid}"]`);
    if (btn) btn.textContent = '▾';
  });
  [...grid.querySelectorAll('.card-scroll')].forEach((b, i) => {
    if (scrolls[i] !== undefined) b.scrollTop = scrolls[i];
  });
  window.scrollTo(0, scrollY);
}

async function descargar(url, payload, fallbackName) {
  const res = await fetch(url, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload)
  });
  if (!res.ok) {
    let msg = 'No se pudo generar el archivo.';
    try { const e = await res.json(); if (e.error) msg = e.error; } catch (_) {}
    toast(msg, 'error');
    return;
  }
  const cd = res.headers.get('Content-Disposition') || '';
  const m = cd.match(/filename="?([^"]+)"?/);
  const name = m ? m[1] : fallbackName;
  const blob = await res.blob();
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(a.href);
}

function exportPedido(code) {
  const sel = document.getElementById('export-suc');
  if (!sel || !sel.value) { toast('Elegí una sucursal', 'error'); return; }
  const url = code === 'CD' ? '/exportar-quantio' : '/exportar/' + code;
  descargar(url, {sucursal: sel.value}, 'pedido_' + code.toLowerCase());
}

async function enviarItem(sku, suc, code, btn) {
  const pill = btn.closest('div');
  const inp  = pill.querySelector('.env-input');
  const cant = parseInt(inp.value, 10) || 0;
  if (cant <= 0) { toast('Poné una cantidad mayor a 0', 'error'); return; }
  setLoading(btn, true);
  const res = await fetch('/api/orden/enviar', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({sku, sucursal: suc, drogueria: code, cantidad: cant})
  });
  const d = await res.json().catch(() => ({}));
  if (res.ok && d.ok) {
    toast(`Envío registrado — ${suc} · ${cant} u. desde ${code}`, 'exito');
    await refrescarOrden();
  } else {
    setLoading(btn, false);
    toast(d.error || 'No se pudo registrar el envío', 'error');
  }
}

async function rotacionItem(sku, suc, btn) {
  const pill = btn.closest('div');
  const inp  = pill.querySelector('.env-input');
  const cant = parseInt(inp.value, 10) || 0;
  if (cant <= 0) { toast('Poné una cantidad mayor a 0', 'error'); return; }
  const ok = await confirmar(`Se cubren ${cant} u. de ${suc} con stock interno (rotación).`,
    {titulo: '¿Cubrir por rotación?', accion: 'Cubrir por rotación', peligro: false});
  if (!ok) return;
  setLoading(btn, true);
  const res = await fetch('/api/orden/rotacion', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({sku, sucursal: suc, cantidad: cant})
  });
  const d = await res.json().catch(() => ({}));
  if (res.ok && d.ok) {
    toast(`Rotación registrada — ${suc} · ${cant} u.`, 'exito');
    await refrescarOrden();
  } else {
    setLoading(btn, false);
    toast(d.error || 'No se pudo registrar la rotación', 'error');
  }
}

async function omitirItem(sku, suc, code) {
  const res = await fetch('/api/orden/omitir', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({sku, sucursal: suc, drogueria: code})
  });
  const d = await res.json().catch(() => ({}));
  if (res.ok && d.ok) { toast('Quitado de esta droguería', 'exito'); refrescarOrden(); }
  else toast(d.error || 'No se pudo quitar', 'error');
}

async function omitirProducto(sku, code) {
  const ok = await confirmar('Se quita para todas las sucursales de esta tarjeta.',
    {titulo: '¿Quitar el producto de esta droguería?', accion: 'Quitar'});
  if (!ok) return;
  const res = await fetch('/api/orden/omitir-producto', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({sku, drogueria: code})
  });
  const d = await res.json().catch(() => ({}));
  if (res.ok && d.ok) { toast('Producto quitado de la droguería', 'exito'); refrescarOrden(); }
  else toast(d.error || 'No se pudo quitar', 'error');
}

async function marcarComprado(drog) {
  const ok = await confirmar('Los productos pendientes de esta droguería pasan a comprados y salen de la orden.',
    {titulo: `¿Marcar ${drog} como comprado?`, accion: 'Marcar comprado', peligro: false});
  if (!ok) return;
  const hoy = new Date().toLocaleDateString('es-AR', {day:'2-digit',month:'2-digit',year:'numeric'});
  const res = await fetch('/api/orden/comprado', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({drogueria: drog, fecha: hoy})
  });
  const d = await res.json().catch(() => ({}));
  if (res.ok && d.ok) {
    toast(`${drog}: ${d.n} producto(s) marcados como comprados`, 'exito');
    refrescarOrden();
  } else {
    toast(d.error || 'No se pudo marcar', 'error');
  }
}

async function marcarInexistente() {
  const skus = [];
  document.querySelectorAll('.qty-input[data-drog="SIN_PRECIO"]').forEach(inp => skus.push(inp.dataset.sku));
  if (!skus.length) { toast('No hay productos sin precio', 'info'); return; }
  const ok = await confirmar('Aparecerán como cancelados con origen "Producto inexistente".',
    {titulo: `¿Marcar ${skus.length} producto(s) como inexistentes?`, accion: 'Marcar inexistentes'});
  if (!ok) return;
  const res = await fetch('/api/orden/inexistente', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({skus})
  });
  const d = await res.json().catch(() => ({}));
  if (res.ok && d.ok) { toast('Marcados como inexistentes', 'exito'); refrescarOrden(); }
  else toast(d.error || 'No se pudo marcar', 'error');
}
</script>
{% endblock %}
```

Notar los cambios de contrato respecto al original: cero `location.reload()`, cero `alert()`/`confirm()`; los endpoints y payloads son EXACTAMENTE los mismos. El botón "Ocultar" de filas overflow (`this.closest('tr').remove()`) queda igual (es solo visual).

- [ ] **Step 4: Verificar** — Run: `$PY -m pytest tests/ -v` → PASS. Greps de control sobre ambos templates: `grep -n "location.reload\|alert(\|confirm(" templates/generar_orden.html templates/_orden_grid.html` → sin resultados.

- [ ] **Step 5: Commit**

```bash
git add templates/generar_orden.html templates/_orden_grid.html
git commit -m "Generar orden: refresco por fragmento sin reload + confirmaciones y toasts del sistema"
```

---

### Task 12: Verificación integral local + deploy al VPS (REQUIERE OK DEL USUARIO)

**Files:** ninguno nuevo (verificación + deploy).

- [ ] **Step 1: Levantar local con datos de prueba**

```bash
cd C:/Users/e.pernochi/Proyectos-Claude/App-pedidos
PEDIDOS_DB_PATH=<scratchpad>/manual-test/pedidos.db PEDIDOS_DATA_DIR=<scratchpad>/manual-test/archivos SECRET_KEY=manual $PY app.py
```

(El catálogo estará vacío sin archivos de datos; para probar Generar orden con datos, copiar los archivos de `Downloads/migracion.zip` extraídos al `PEDIDOS_DATA_DIR` y el `pedidos.db` del scratchpad al `PEDIDOS_DB_PATH`.)

- [ ] **Step 2: Checklist manual (browser en localhost:8080)**

Como sucursal (CERRO/cerro123): login (tarjeta nueva) → nueva solicitud (buscar, cantidades, toasts de validación, ver solicitud, confirmar con spinner) → confirmado (metric-cards, badges, cancelar ítem con modal → tabla se refresca sin recargar, restaurar) → mis pedidos (badges nuevos).
Como admin: consolidado (metric-cards, click fila → resalta + detalle) → generar orden: expandir detalles, **Enviar** (toast + la pill desaparece sin recargar la página, el scroll no salta), **Rotación** (modal → toast → refresco), **omitir** ítem y producto (modal), **marcar comprado** (modal → tarjeta se vacía), exportar (descarga o toast de error si no hay envíos), con filtro de sucursal activo repetir Enviar (el filtro se preserva). Encadenar 3+ acciones seguidas verificando que los detalles expandidos se mantienen.
Responsive: DevTools a 375px en login, nueva solicitud y mis pedidos (navbar colapsa, tablas scrollean dentro de su tarjeta).

- [ ] **Step 3: PEDIR OK AL USUARIO para deploy** — mostrarle el resultado local (screenshots o que lo pruebe él) y confirmar el deploy al VPS.

- [ ] **Step 4: Deploy quirúrgico (tras OK)**

```bash
cd C:/Users/e.pernochi/Proyectos-Claude/App-pedidos
git archive --format=tar ui-redesign | ssh -p 5930 root@179.43.123.251 \
  "rm -rf /opt/App-Pedidos && mkdir -p /opt/App-Pedidos && tar xf - -C /opt/App-Pedidos"
ssh -p 5930 root@179.43.123.251 \
  "cd /opt/farmacias-red-comparador && docker compose -f docker-compose.prod.yml up -d --build pedidos"
```

Verificar: `curl -I https://pedidos.farmaciasred.com/health` → 200; abrir la web y repetir el checklist clave (login, generar orden con una acción). El comparador no se toca. Los datos reales del volumen (`/data`) persisten a través del rebuild.

- [ ] **Step 5: Commit final de plan actualizado** (checkboxes marcados) y aviso al usuario para que revise en producción y se lo muestre a Day.

---

## Self-Review (hecho al escribir el plan)

- **Cobertura del spec:** tokens/tipografía → Task 4-5; micro-UX API → Task 5; login → 6; nueva_solicitud → 7; mis_pedidos/actualizar_datos → 8; confirmado + fragmento ítems → 9; consolidado → 10; generar_orden restyle + refresco por fragmento + preservación de estado → 3 y 11; índices SQLite → 2; responsive → 4 (media queries) + checklist 12; verificación y deploy → 12. Sin huecos.
- **Placeholders:** Task 8 Step 2 delega criterio sobre actualizar_datos (template de 52 líneas revisado en sesión: usa tabla simple; el criterio "envolver en tarjeta + btn-brand" es suficiente y verificable por grep sin hex). Aceptado conscientemente como el único paso semi-abierto.
- **Consistencia de nombres:** `toast/confirmar/setLoading` (Task 5) usados en 7/9/11; `refrescarOrden` definido y usado solo en 11; `_armar_orden` y rutas de fragmento consistentes entre 3, 9 y 11; clases CSS de Task 4 referenciadas idénticas en 6-11.
