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
