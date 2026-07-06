"""CSRF: los POST del navegador requieren token; el endpoint del cron queda
exento (se autentica por X-Cron-Token, sin sesión)."""
import app as app_module


def _con_csrf(client):
    app_module.app.config['WTF_CSRF_ENABLED'] = True
    return client


def test_post_sin_token_es_rechazado(client):
    _con_csrf(client)
    try:
        r = client.post('/login', data={'username': 'CERRO', 'password': 'cerro123'})
        assert r.status_code == 400
    finally:
        app_module.app.config['WTF_CSRF_ENABLED'] = False


def test_api_post_sin_token_es_rechazado(sucursal):
    _con_csrf(sucursal)
    try:
        r = sucursal.post('/api/carrito/set', json={'sucursal': 'CERRO', 'sku': '1', 'cantidad': 1})
        assert r.status_code == 400
    finally:
        app_module.app.config['WTF_CSRF_ENABLED'] = False


def test_endpoint_cron_exento_de_csrf(client):
    """Sin sesión y sin CSRF token: debe llegar a la lógica de auth propia
    (403 por token inválido), no morir en 400 de CSRF."""
    _con_csrf(client)
    try:
        r = client.post('/api/fuentes/refrescar', headers={'X-Cron-Token': 'invalido'})
        assert r.status_code == 403
    finally:
        app_module.app.config['WTF_CSRF_ENABLED'] = False


def test_login_con_token_funciona(client):
    """El form de login rinde el token y el POST con token pasa."""
    _con_csrf(client)
    try:
        page = client.get('/login').data.decode()
        import re
        m = re.search(r'name="csrf_token" value="([^"]+)"', page)
        assert m, 'el form de login no rinde csrf_token'
        r = client.post('/login', data={
            'username': 'CERRO', 'password': 'cerro123', 'csrf_token': m.group(1)})
        assert r.status_code in (200, 302)
    finally:
        app_module.app.config['WTF_CSRF_ENABLED'] = False
