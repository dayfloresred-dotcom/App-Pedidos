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
