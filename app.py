import os
from flask import Flask, render_template, request, session, redirect, url_for, jsonify, flash, Response
from datetime import date, datetime
from config import SECRET_KEY, SUCURSAL_NAMES, ADMIN_USER
from database import (init_db, crear_solicitud, get_solicitud_detalle, get_todas_solicitudes,
                       get_consolidado, get_detalle_por_sucursal, marcar_comprado, cancelar_solicitud,
                       get_db, actualizar_droguerias_pendientes,
                       get_items_detalle, marcar_item_generado, desmarcar_item_generado,
                       cancelar_producto, cancelar_producto_sucursal, cancelar_item, get_item_sucursal,
                       marcar_comprado_drogueria, marcar_inexistente,
                       registrar_envio, get_envios, get_envios_sucursal, get_envios_por_drogueria)
from data_loader import buscar_productos, get_laboratorios, load_productos
from auth import seed_users, verify_user, login_required, admin_required
from mail_service import enviar_notificacion
from export_service import generar_suizo, generar_sud, generar_quantio

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config['TEMPLATES_AUTO_RELOAD'] = True

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
    filtro_suc = request.args.get('suc','')
    if session.get('rol') == 'admin':
        solic = get_todas_solicitudes(sucursal_filtro=filtro_suc or None)
    else:
        solic = get_todas_solicitudes(sucursal_filtro=session['username'])
    return render_template('mis_pedidos.html',
        solicitudes=solic, sucursales=SUCURSAL_NAMES, filtro_suc=filtro_suc)

@app.route('/confirmado/<int:sol_id>')
@login_required
def ver_solicitud(sol_id):
    sol, items = get_solicitud_detalle(sol_id)
    if not sol:
        flash('Solicitud no encontrada', 'danger')
        return redirect(url_for('mis_pedidos'))
    envios = get_envios_sucursal(sol['sucursal'])
    return render_template('confirmado.html', sol=sol, items=items, envios=envios)

@app.route('/solicitud/<int:sol_id>/cancelar', methods=['POST'])
@login_required
def cancelar(sol_id):
    sol, _ = get_solicitud_detalle(sol_id)
    if not sol:
        flash('Solicitud no encontrada', 'danger')
        return redirect(url_for('mis_pedidos'))
    # Solo puede cancelar el dueño del pedido o el admin
    if session.get('rol') != 'admin' and sol['sucursal'] != session.get('username'):
        flash('No tenés permiso para cancelar este pedido', 'danger')
        return redirect(url_for('mis_pedidos'))
    if sol['estado'] != 'pendiente':
        flash('Solo se pueden cancelar pedidos pendientes', 'warning')
        return redirect(url_for('ver_solicitud', sol_id=sol_id))
    cancelar_solicitud(sol_id)
    flash(f'Pedido {sol["numero"]} cancelado', 'warning')
    return redirect(url_for('mis_pedidos'))

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
    prods    = get_consolidado()
    prod_map = {p['sku']: p for p in load_productos()}
    orden    = {'DROGUERIA RED': [], 'SUD': [], 'SUIZO': [], 'SIN_PRECIO': []}

    for p in prods:
        suc_list = [s.strip() for s in (p.get('sucursales') or '').split(',') if s.strip()]
        chips = ' '.join(f'<span class="chip-suc">{s}</span>' for s in suc_list[:3])
        if len(suc_list) > 3:
            chips += f' <span class="chip-suc">+{len(suc_list)-3}</span>'
        # Add CD stock quantity
        base     = prod_map.get(p['sku'], {})
        raw_cd   = base.get('stock_cd', 0)
        stock_cd = raw_cd if isinstance(raw_cd, int) else (1 if raw_cd == 'SI' else 0)
        drog_ext = base.get('drog_ext', '')
        # Detalle por sucursal con estado de orden (para marcar generado y export Quantio)
        detalle = get_items_detalle(p['sku'])
        for d in detalle:
            d['enviado'] = get_envios(d['sucursal'], p['sku'])
        item     = {**p, 'sucursales_str': chips, 'stock_cd': stock_cd, 'drog_ext': drog_ext,
                    'es_overflow': False, 'detalle_suc': detalle}
        drog     = (p.get('drogueria') or '').upper()
        # Código de droguería que se registra al marcar generado (lo que ve la sucursal)
        DROG_CODE = {'DROGUERIA RED': 'CD', 'SUD': 'SUD', 'SUIZO': 'SUIZO'}
        item['drog_code'] = DROG_CODE.get(drog, '')
        if drog == 'DROGUERIA RED':
            orden['DROGUERIA RED'].append(item)
            # If CD stock insufficient, add overflow order to external droguería
            overflow = p['total'] - stock_cd
            if overflow > 0 and drog_ext in ('SUD', 'SUIZO'):
                ovf_det = get_items_detalle(p['sku'])
                for d in ovf_det:
                    d['enviado'] = get_envios(d['sucursal'], p['sku'])
                ovf_code = {'SUD': 'SUD', 'SUIZO': 'SUIZO'}.get(drog_ext, '')
                overflow_item = {**item, 'total': overflow, 'es_overflow': True, 'detalle_suc': ovf_det, 'drog_code': ovf_code}
                orden[drog_ext].append(overflow_item)
        elif drog == 'SUD':
            orden['SUD'].append(item)
        elif drog == 'SUIZO':
            orden['SUIZO'].append(item)
        else:
            orden['SIN_PRECIO'].append(item)

    # Sucursales presentes en el pedido (para el desplegable de export por sucursal)
    sucs_orden = sorted({d['sucursal'] for its in orden.values() for it in its for d in it['detalle_suc']})

    return render_template('generar_orden.html',
        orden={k: v for k, v in orden.items() if v},
        sucs_orden=sucs_orden,
        hoy=date.today().strftime('%d/%m/%Y'))

# ── API endpoints ──────────────────────────────────────────────────────────
@app.route('/api/productos')
@login_required
def api_productos():
    q   = request.args.get('q', '')
    lab = request.args.get('lab', '')
    suc = request.args.get('suc', '') or session.get('username', '')
    results = buscar_productos(q=q, laboratorio=lab, sucursal=suc)[:200]
    return jsonify([{
        'sku':         p['sku'],
        'ean':         p['ean'],
        'descripcion': p['descripcion'],
        'laboratorio': p['laboratorio'],
        'drogueria':   p['drogueria'],
        'stock_real':  p['stock_real'].get(suc, 0) if suc and suc != 'admin' else 0,
        'stock_cd':    'SI' if (p.get('stock_cd') or 0) not in (0, '', 'NO') else 'NO',
    } for p in results])

@app.route('/api/solicitud', methods=['POST'])
@login_required
def api_crear_solicitud():
    data     = request.get_json()
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
    sku  = request.args.get('sku', '')
    rows = get_detalle_por_sucursal(sku)
    prod_map = {p['sku']: p for p in load_productos()}
    prod = prod_map.get(sku, {})
    result = []
    for r in rows:
        suc = r['sucursal']
        stock     = prod.get('stock_real', {}).get(suc, 0)
        necesidad = prod.get('necesidad', {}).get(suc, 0)
        # ventas field added in v2; fallback: necesidad + stock
        ventas_map = prod.get('ventas')
        if ventas_map is not None:
            ventas = ventas_map.get(suc, 0)
        else:
            ventas = necesidad + stock  # reconstruct: necesidad = ventas - stock
        result.append({
            'sucursal':  suc,
            'cantidad':  r['cantidad'],
            'stock':     stock,
            'ventas':    ventas,
            'necesidad': necesidad,
        })
    return jsonify(result)

@app.route('/api/orden/remove', methods=['POST'])
@login_required
@admin_required
def api_orden_remove():
    # Note: This removes pending items from display by marking them in session
    # For simplicity, we return ok and client reloads — actual removal would need
    # a separate "orden_override" table. For now this is a no-op that refreshes.
    return jsonify({'ok': True})

@app.route('/api/orden/comprado', methods=['POST'])
@login_required
@admin_required
def api_marcar_comprado():
    """Marca como comprados SOLO los productos de esa droguería (a nivel item)."""
    data  = request.get_json(silent=True) or {}
    drog  = (data.get('drogueria') or '').strip()
    fecha = data.get('fecha') or date.today().strftime('%d/%m/%Y')
    if not drog:
        return jsonify({'error': 'Falta droguería'}), 400
    n = marcar_comprado_drogueria(drog, fecha)
    return jsonify({'ok': True, 'n': n})

@app.route('/api/orden/inexistente', methods=['POST'])
@login_required
@admin_required
def api_inexistente():
    """Marca productos sin precio como inexistentes (cancelados con origen 'Producto inexistente')."""
    skus = (request.get_json(silent=True) or {}).get('skus') or []
    for sku in skus:
        sku = str(sku).strip()
        if sku:
            marcar_inexistente(sku)
    return jsonify({'ok': True, 'n': len(skus)})

@app.route('/api/orden/enviar', methods=['POST'])
@login_required
@admin_required
def api_enviar():
    """Registra cuántas unidades se envían a una sucursal desde una droguería (acumulativo)."""
    data = request.get_json(silent=True) or {}
    sku  = str(data.get('sku') or '').strip()
    suc  = (data.get('sucursal') or '').strip()
    drog = (data.get('drogueria') or '').strip().upper()
    try:
        cant = int(data.get('cantidad'))
    except (TypeError, ValueError):
        cant = 0
    if not (sku and suc and drog):
        return jsonify({'error': 'Faltan datos'}), 400
    registrar_envio(suc, sku, drog, cant)
    # marca el item como generado (para el contador y el estado de la sucursal)
    if cant > 0:
        marcar_item_generado(sku, suc, drog, date.today().strftime('%d/%m/%Y'))
    return jsonify({'ok': True, 'enviado': get_envios(suc, sku)})

@app.route('/api/orden/generar-item', methods=['POST'])
@login_required
@admin_required
def api_generar_item():
    """Marca como generado el pedido de un producto para una sucursal puntual."""
    data = request.get_json(silent=True) or {}
    sku  = str(data.get('sku') or '').strip()
    suc  = (data.get('sucursal') or '').strip()
    drog = (data.get('drogueria') or '').strip().upper()
    if not (sku and suc and drog):
        return jsonify({'error': 'Faltan datos'}), 400
    marcar_item_generado(sku, suc, drog, date.today().strftime('%d/%m/%Y'))
    return jsonify({'ok': True})

@app.route('/api/orden/desmarcar-item', methods=['POST'])
@login_required
@admin_required
def api_desmarcar_item():
    """Revierte el marcado de generado de un producto para una sucursal."""
    data = request.get_json(silent=True) or {}
    sku  = str(data.get('sku') or '').strip()
    suc  = (data.get('sucursal') or '').strip()
    if not (sku and suc):
        return jsonify({'error': 'Faltan datos'}), 400
    desmarcar_item_generado(sku, suc)
    return jsonify({'ok': True})

@app.route('/api/orden/cancelar-producto', methods=['POST'])
@login_required
@admin_required
def api_cancelar_producto():
    """Cancela un producto para todas las sucursales pendientes (vista compras)."""
    sku = str((request.get_json(silent=True) or {}).get('sku') or '').strip()
    if not sku:
        return jsonify({'error': 'Falta sku'}), 400
    cancelar_producto(sku)
    return jsonify({'ok': True})

@app.route('/api/orden/cancelar-item', methods=['POST'])
@login_required
@admin_required
def api_cancelar_item_suc():
    """Cancela un producto para una sucursal puntual (vista compras)."""
    data = request.get_json(silent=True) or {}
    sku  = str(data.get('sku') or '').strip()
    suc  = (data.get('sucursal') or '').strip()
    if not (sku and suc):
        return jsonify({'error': 'Faltan datos'}), 400
    cancelar_producto_sucursal(sku, suc)
    return jsonify({'ok': True})

@app.route('/api/item/cancelar', methods=['POST'])
@login_required
def api_cancelar_item_id():
    """Cancela un ítem puntual de un pedido (vista sucursal). Permiso: admin o dueño."""
    data = request.get_json(silent=True) or {}
    try:
        item_id = int(data.get('item_id'))
    except (TypeError, ValueError):
        return jsonify({'error': 'Falta el ítem'}), 400
    suc = get_item_sucursal(item_id)
    if suc is None:
        return jsonify({'error': 'Ítem no encontrado'}), 404
    if session.get('rol') != 'admin' and session.get('username') != suc:
        return jsonify({'error': 'Sin permiso'}), 403
    cancelar_item(item_id)
    return jsonify({'ok': True})

# ── Export routes ──────────────────────────────────────────────────────────
@app.route('/exportar/<drogueria>', methods=['GET', 'POST'])
@login_required
@admin_required
def exportar(drogueria):
    """Exporta el pedido de UNA sucursal para esa droguería, con las cantidades manuales cargadas."""
    drog = drogueria.upper()
    data = request.get_json(silent=True) or {}
    sucursal = (data.get('sucursal') or '').strip()
    if not sucursal:
        return jsonify({'error': 'Elegí una sucursal'}), 400

    prod_map = {p['sku']: p for p in load_productos()}
    items = []
    for it in data.get('items', []):
        try:
            cant = max(0, int(it['cantidad']))
        except (KeyError, ValueError, TypeError):
            continue
        if cant <= 0:
            continue
        base = prod_map.get(str(it.get('sku')), {})
        items.append({
            'ean':         it.get('ean') or base.get('ean', ''),
            'troquel':     base.get('troquel', '0000000'),
            'descripcion': base.get('descripcion', ''),
            'cantidad':    cant,
        })
    if not items:
        return jsonify({'error': f'{sucursal} no tiene cantidades cargadas para {drog}.'}), 400

    suc_slug = ''.join(c if c.isalnum() else '_' for c in sucursal.lower())
    if drog == 'SUIZO':
        content  = generar_suizo(items)
        filename = f'suizo_{suc_slug}_{date.today().strftime("%d%m%y")}.arg'
    else:
        content  = generar_sud(items)
        filename = f'sud_{suc_slug}_{date.today().strftime("%d%m%y")}.dds'

    return Response(
        content,
        mimetype='application/octet-stream',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'}
    )

@app.route('/exportar-quantio', methods=['POST'])
@login_required
@admin_required
def exportar_quantio():
    """Pedido Quantio (CD) por sucursal con cantidades editadas."""
    data     = request.get_json(silent=True) or {}
    sucursal = (data.get('sucursal') or '').strip()
    if not sucursal:
        return jsonify({'error': 'Falta sucursal'}), 400

    prod_map = {p['sku']: p for p in load_productos()}
    items = []
    for it in data.get('items', []):
        try:
            cant = max(0, int(it['cantidad']))
        except (KeyError, ValueError, TypeError):
            continue
        if cant <= 0:
            continue
        base = prod_map.get(str(it.get('sku')), {})
        items.append({
            'ean':         it.get('ean') or base.get('ean', ''),
            'troquel':     base.get('troquel_pres') or base.get('troquel') or '',
            'cantidad':    cant,
        })

    if not items:
        return jsonify({'error': 'Sin productos para esta sucursal'}), 400

    content   = generar_quantio(items)
    suc_slug  = ''.join(c if c.isalnum() else '_' for c in sucursal.lower())
    filename  = f'quantio_{suc_slug}_{date.today().strftime("%d%m%y")}.txt'
    return Response(
        content.encode('latin-1', errors='replace'),
        mimetype='text/plain',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'}
    )

@app.route('/actualizar-datos', methods=['GET', 'POST'])
@login_required
@admin_required
def actualizar_datos():
    from config import (PRESUPUESTO_CSV, STOCK_CD_CSV, LISTADO_STOCK_CSV,
                        PRECIOS_SUD_TXT, PRECIOS_SUIZO_PERFU, PRECIOS_SUIZO_INS,
                        PRECIOS_DDS_XLSX, PRECIOS_SUIZO_CMP_XLSX)
    import data_loader

    ARCHIVOS = {
        'presupuesto':         {'label': 'Presupuesto (ventas, stock y stock CD)',  'path': PRESUPUESTO_CSV,       'accept': '.csv,.txt', 'diario': True},
        'precios_dds':         {'label': 'Lista DDS / Sud (comparador, precio final)', 'path': PRECIOS_DDS_XLSX,    'accept': '.xlsx',     'diario': False},
        'precios_suizo_cmp':   {'label': 'Lista Suizo (comparador, precio final)',   'path': PRECIOS_SUIZO_CMP_XLSX,'accept': '.xlsx',     'diario': False},
        'precios_sud':         {'label': 'Precios SUD (formato viejo .txt)',         'path': PRECIOS_SUD_TXT,       'accept': '.txt',      'diario': False},
        'precios_suizo_perfu': {'label': 'Precios Suizo Perfumería (viejo)',         'path': PRECIOS_SUIZO_PERFU,   'accept': '.xls,.xlsx','diario': False},
        'precios_suizo_ins':   {'label': 'Precios Suizo Insumos (viejo)',            'path': PRECIOS_SUIZO_INS,     'accept': '.xls,.xlsx','diario': False},
    }

    if request.method == 'POST':
        updated = []
        for field, cfg in ARCHIVOS.items():
            f = request.files.get(field)
            if f and f.filename:
                os.makedirs(os.path.dirname(cfg['path']), exist_ok=True)
                f.save(cfg['path'])
                updated.append(cfg['label'])
        if updated:
            # Forzar recarga completa: borrar cache en disco y en memoria
            if os.path.exists(data_loader.CACHE_FILE):
                os.remove(data_loader.CACHE_FILE)
            data_loader._productos = None
            nuevos = load_productos()
            prod_map = {p['sku']: p for p in nuevos}
            n_items = actualizar_droguerias_pendientes(prod_map)
            flash(f'✓ Actualizados: {", ".join(updated)}. {len(nuevos)} productos recargados. {n_items} pedidos pendientes actualizados.', 'success')
        else:
            flash('No seleccionaste ningún archivo.', 'warning')
        return redirect(url_for('actualizar_datos'))

    archivos_info = {}
    for field, cfg in ARCHIVOS.items():
        path = cfg['path']
        if os.path.exists(path):
            mtime = os.path.getmtime(path)
            info = {'existe': True, 'fecha': datetime.fromtimestamp(mtime).strftime('%d/%m/%Y %H:%M')}
        else:
            info = {'existe': False, 'fecha': '—'}
        archivos_info[field] = {**cfg, **info, 'nombre': os.path.basename(path)}
    return render_template('actualizar_datos.html', archivos=archivos_info)

@app.errorhandler(403)
def forbidden(e):
    return render_template('login.html', error='Acceso denegado'), 403

init_db()
seed_users()

if __name__ == '__main__':
    print("Iniciando App Pedidos Farmacias Red...")
    load_productos()
    print("Listo! Abrí tu navegador en: http://localhost:8080")
    app.run(debug=False, use_reloader=False, host='0.0.0.0', port=8080)
