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


def test_fragmento_confirmado_404_si_no_existe(admin):
    assert admin.get('/confirmado/99999/fragmento').status_code == 404


def test_fragmento_confirmado(sucursal):
    r = sucursal.post('/api/solicitud', json={'items': [
        {'sku': 'T1', 'ean': '779', 'descripcion': 'Prueba', 'laboratorio': 'Lab', 'cantidad': 2}
    ]})
    sol_id = r.get_json()['sol_id']
    f = sucursal.get(f'/confirmado/{sol_id}/fragmento')
    assert f.status_code == 200
    assert b'Prueba' in f.data


def test_filtro_ped_no_numerico_no_rompe(admin):
    """get_consolidado/get_items_detalle hacen int() sobre los ids del filtro:
    un ?ped= tocado a mano tiraba 500 en vez de ignorarse."""
    assert admin.get('/generar-orden?ped=abc').status_code == 200
    assert admin.get('/generar-orden/fragmento?suc=&ped=abc').status_code == 200
