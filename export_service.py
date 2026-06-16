def generar_suizo(items):
    """
    SUIZO .arg format:
    EAN (13 chars) + 30 spaces + quantity (3 digits zero-padded)
    Total line length: 46 chars
    """
    lines = []
    for it in items:
        ean = (it.get('ean') or '').ljust(13)[:13]
        qty = str(it['cantidad']).zfill(3)
        lines.append(f"{ean}{'':30}{qty}")
    return '\n'.join(lines)

def generar_sud(items):
    """
    SUD .dds format:
    EAN (13) + troquel (7) + product name (33, truncated/padded) + quantity
    """
    lines = []
    for it in items:
        ean     = (it.get('ean') or '').ljust(13)[:13]
        troquel = (it.get('troquel') or '0000000').zfill(7)[:7]
        nombre  = (it.get('descripcion') or '').ljust(33)[:33]
        qty     = str(it['cantidad'])
        lines.append(f"{ean}{troquel}{nombre}{qty}")
    return '\n'.join(lines)

def generar_quantio(items):
    """
    QUANTIO .csv format (pedido a CD / Droguería Red):
    EAN;Descripción;Cantidad  (separador ';', terminador CRLF)
    """
    lines = []
    for it in items:
        ean = (it.get('ean') or '').strip()
        # El ';' es el delimitador: limpiarlo de la descripción
        nombre = (it.get('descripcion') or '').replace(';', ' ').strip()
        qty = str(it['cantidad'])
        lines.append(f"{ean};{nombre};{qty}")
    return '\r\n'.join(lines)
