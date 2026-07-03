import importlib
import os


def test_config_fuentes_defaults_y_env(monkeypatch):
    monkeypatch.setenv('PLEX_HOST', 'h1')
    monkeypatch.setenv('PLEX_PORT', '6613')
    monkeypatch.setenv('VENTAS_VENTANA_DIAS', '45')
    import config
    importlib.reload(config)
    assert config.PLEX['host'] == 'h1' and config.PLEX['port'] == 6613
    assert config.VENTAS_VENTANA_DIAS == 45
    assert config.FUENTES_RUBROS == ['Perfumería', 'Accesorios']
    assert config.fuente_mysql_configurada(config.PLEX) is False  # falta user/pass/db
    monkeypatch.setenv('PLEX_USER', 'u')
    monkeypatch.setenv('PLEX_PASSWORD', 'p')
    monkeypatch.setenv('PLEX_DB', 'onze_center')
    importlib.reload(config)
    assert config.fuente_mysql_configurada(config.PLEX) is True
    # limpiar env ANTES del reload final, para dejar config con defaults reales
    for var in ['PLEX_HOST', 'PLEX_PORT', 'PLEX_USER', 'PLEX_PASSWORD', 'PLEX_DB',
                'VENTAS_VENTANA_DIAS']:
        monkeypatch.delenv(var, raising=False)
    importlib.reload(config)
    assert config.PLEX['host'] == ''  # config quedó con defaults, sin valores de test
    assert config.VENTAS_VENTANA_DIAS == 60
