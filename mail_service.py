import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from config import MAIL_SERVER, MAIL_PORT, MAIL_USERNAME, MAIL_PASSWORD, MAIL_ADMIN

def enviar_notificacion(numero, sucursal, items):
    """Send email notification to admin when a new order is created."""
    if not MAIL_USERNAME or not MAIL_PASSWORD:
        print(f'[MAIL] Skipped (not configured). Order: {numero}')
        return

    body_lines = [
        f'Nueva solicitud recibida: <b>{numero}</b>',
        f'Sucursal: <b>{sucursal}</b>',
        f'Productos solicitados: <b>{len(items)}</b>',
        '<br><table border="1" cellpadding="4" style="border-collapse:collapse">',
        '<tr><th>EAN</th><th>Producto</th><th>Laboratorio</th><th>Cantidad</th></tr>',
    ]
    for it in items:
        body_lines.append(
            f'<tr><td>{it.get("ean","")}</td><td>{it["descripcion"]}</td>'
            f'<td>{it.get("laboratorio","")}</td><td>{it["cantidad"]}</td></tr>'
        )
    body_lines.append('</table>')

    msg = MIMEMultipart('alternative')
    msg['Subject'] = f'[Farmacias Red] Nueva solicitud {numero} — {sucursal}'
    msg['From']    = MAIL_USERNAME
    msg['To']      = MAIL_ADMIN
    msg.attach(MIMEText('\n'.join(body_lines), 'html'))

    try:
        with smtplib.SMTP(MAIL_SERVER, MAIL_PORT) as s:
            s.starttls()
            s.login(MAIL_USERNAME, MAIL_PASSWORD)
            s.sendmail(MAIL_USERNAME, MAIL_ADMIN, msg.as_string())
        print(f'[MAIL] Sent notification for {numero}')
    except Exception as e:
        print(f'[MAIL] Error sending: {e}')
