"""Tests de las features integradas desde origin/main (commits de Dai):
carrito persistente, observación por producto, ranking, export Sud de ancho
fijo y hora local de archivos. El código llegó por merge sin tests — estos
lo caracterizan para que la integración no lo rompa."""
from datetime import datetime, timedelta, timezone

from config import local_from_ts, now_local
from database import (init_db, crear_solicitud, get_solicitud_detalle, get_ranking,
                      carrito_set, carrito_set_obs, get_carrito, carrito_clear)
from export_service import generar_sud


def test_carrito_set_get_actualizar_y_borrar_en_cero():
    init_db()
    carrito_clear('CERRO')
    carrito_set('CERRO', '111', '779000000001', 'PRODUCTO A', 'LAB X', 'SUD', 3)
    carrito_set('CERRO', '222', '779000000002', 'PRODUCTO B', 'LAB Y', '', 1, 'urgente')
    items = get_carrito('CERRO')
    assert [(i['sku'], i['cantidad'], i['observacion']) for i in items] == \
        [('111', 3, None), ('222', 1, 'urgente')]
    # upsert: misma sucursal+sku actualiza cantidad
    carrito_set('CERRO', '111', '779000000001', 'PRODUCTO A', 'LAB X', 'SUD', 5)
    assert get_carrito('CERRO')[0]['cantidad'] == 5
    # cantidad 0 elimina la fila
    carrito_set('CERRO', '111', '', '', '', '', 0)
    assert [i['sku'] for i in get_carrito('CERRO')] == ['222']
    # el carrito es por sucursal
    assert get_carrito('RECTA') == []
    carrito_clear('CERRO')
    assert get_carrito('CERRO') == []


def test_carrito_obs_y_confirmar_persiste_observacion():
    init_db()
    carrito_clear('RECTA')
    carrito_set('RECTA', '333', '779000000003', 'PRODUCTO C', 'LAB Z', 'CD', 2)
    carrito_set_obs('RECTA', '333', 'vence 08/26')
    items = get_carrito('RECTA')
    assert items[0]['observacion'] == 'vence 08/26'
    numero, sol_id = crear_solicitud('RECTA', 'RECTA', items)
    _, det = get_solicitud_detalle(sol_id)
    assert det[0]['observacion'] == 'vence 08/26'
    carrito_clear('RECTA')


def test_get_ranking_periodos_y_laboratorio():
    init_db()
    hoy = now_local().strftime('%d/%m/%Y %H:%M')
    crear_solicitud('URCA', 'URCA', [
        {'sku': '901', 'descripcion': 'RANK UNO', 'laboratorio': 'LAB RANK', 'cantidad': 7},
        {'sku': '902', 'descripcion': 'RANK DOS', 'laboratorio': 'LAB RANK', 'cantidad': 2},
    ])
    labs, prods = get_ranking('pendiente')
    labs_d, prods_d = dict(labs), {(d, l): u for d, l, u in prods}
    assert labs_d.get('LAB RANK', 0) >= 9
    assert prods_d.get(('RANK UNO', 'LAB RANK'), 0) >= 7
    # 'todo' incluye al menos lo mismo que 'pendiente'
    labs_t, _ = get_ranking('todo')
    assert dict(labs_t).get('LAB RANK', 0) >= labs_d.get('LAB RANK', 0)
    # 'mes' corre sin romper con fechas dd/mm/yyyy
    labs_m, _ = get_ranking('mes')
    assert isinstance(labs_m, list) and hoy  # smoke: no exceptions


def test_generar_sud_ancho_fijo_54():
    linea = generar_sud([{
        'ean': '7791234567890',
        'troquel': 'A12-345',           # se queda solo con dígitos y rellena a 7
        'descripcion': 'PRODUCTO CON NOMBRE MUY LARGO QUE SE CORTA 123',
        'cantidad': 12,
    }])
    assert len(linea) == 54
    assert linea[0:13] == '7791234567890'
    assert linea[13:20] == '0012345'
    assert linea[20:50] == 'PRODUCTO CON NOMBRE MUY LARGO '
    assert linea[50:54] == '  12'
    # múltiples líneas separadas por CRLF
    dos = generar_sud([{'ean': '1', 'troquel': '1', 'descripcion': 'X', 'cantidad': 1}] * 2)
    assert dos.count('\r\n') == 1


def test_local_from_ts_es_utc_menos_3():
    ts = datetime(2026, 7, 6, 15, 0, 0, tzinfo=timezone.utc).timestamp()
    local = local_from_ts(ts)
    assert local.hour == 12
    assert local.utcoffset() == timedelta(hours=-3)
