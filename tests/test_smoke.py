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


def test_base_incluye_sistema(admin):
    r = admin.get('/mis-pedidos')
    assert b'ui.js' in r.data
    assert b'fonts.googleapis.com' in r.data
    assert b'navbar-app' in r.data
