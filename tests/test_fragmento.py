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
