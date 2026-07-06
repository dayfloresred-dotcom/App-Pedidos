# Migración de producción: PythonAnywhere → VPS DonWeb

Fecha: 2026-07-02

## Contexto

Producción corre hoy en https://farmaciasred.pythonanywhere.com (cuenta gratuita).
Limitaciones que motivan la migración:

- Sin dominio propio (la cuenta gratuita no lo permite).
- Sin conexiones salientes libres: no puede conectarse al Postgres de Supabase
  (BI) ni al Postgres del comparador, que son la base del plan de integración.
- Sin SSH, CPU limitada, y hay que "renovar" la app cada 3 meses a mano.

Destino: el VPS de DonWeb donde ya corre el comparador
(`/opt/farmacias-red-comparador`, stack docker-compose con Caddy que maneja
HTTPS automático). App-Pedidos entra como un servicio más de ese stack, servido
en `pedidos.farmaciasred.com`.

Los cambios de código de esta rama (`deploy-vps`):

- `Dockerfile` + `.dockerignore` (imagen python-slim + gunicorn, 1 worker).
- `config.py` lee `PEDIDOS_DB_PATH`, `PEDIDOS_DATA_DIR`, `SECRET_KEY`,
  `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_ADMIN` de variables de entorno.
- **Los secretos hardcodeados se eliminaron del código**: sin `MAIL_USERNAME`/
  `MAIL_PASSWORD` las notificaciones por mail se omiten (la app sigue
  funcionando), y sin `SECRET_KEY` se genera una clave aleatoria por arranque
  (las sesiones se caen en cada reinicio — solo aceptable en desarrollo).
  Ojo: si esta rama se mergea y se despliega en PythonAnywhere SIN configurar
  las variables, dejan de salir los mails y los usuarios se desloguean en cada
  reload. Es intencional: la contraseña vieja está comprometida y hay que
  rotarla igual.
- Endpoint `GET /health` para healthchecks.

Del lado del comparador (rama `feat/hostear-app-pedidos`): servicio `pedidos`
en `docker-compose.prod.yml`, bloque `pedidos.farmaciasred.com` en el
Caddyfile y variables `PEDIDOS_*` en `.env.prod.example`.

## Pre-requisitos

1. Registro DNS tipo A: `pedidos.farmaciasred.com` → IP del VPS (mismo valor
   que `comparador.farmaciasred.com`). Se administra donde esté el DNS de
   `farmaciasred.com` (DonWeb).
2. Acceso SSH al VPS.
3. **Credenciales rotadas ANTES del cutover** (coordinar con Day):
   - Revocar la contraseña de aplicación de Gmail actual (está expuesta en el
     historial del repo público) y generar una nueva. La nueva vive SOLO en el
     `.env` del VPS, nunca en el código.
   - Generar `SECRET_KEY` nueva: `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`.

## Pasos en el VPS

```bash
# 1. Clonar App-Pedidos como repo hermano del comparador
cd /opt
git clone https://github.com/dayfloresred-dotcom/App-Pedidos.git App-Pedidos
cd App-Pedidos && git checkout deploy-vps   # hasta que se mergee a main

# 2. Actualizar el comparador (trae compose + Caddyfile nuevos)
cd /opt/farmacias-red-comparador
git pull --ff-only                          # con feat/hostear-app-pedidos mergeada

# 3. Completar variables nuevas en .env (ver .env.prod.example):
#    PEDIDOS_SECRET_KEY, PEDIDOS_MAIL_USERNAME, PEDIDOS_MAIL_PASSWORD, PEDIDOS_MAIL_ADMIN
nano .env

# 4. Build y arranque del servicio nuevo (no toca los demás)
docker compose -f docker-compose.prod.yml up -d --build pedidos

# 5. Recargar Caddy para que tome el sitio nuevo
docker compose -f docker-compose.prod.yml restart caddy

# 6. Verificar
docker compose -f docker-compose.prod.yml ps
curl -I https://pedidos.farmaciasred.com/health   # esperado: 200
```

Con esto la app arranca VACÍA (base nueva, usuarios semilla). Falta migrar los
datos reales.

## Deploy de cambios (post-cutover 2026-07-06)

`/opt/App-Pedidos` es un clone de este repo (rama `main`). Para deployar:

```bash
ssh -p 5930 root@179.43.123.251
cd /opt/App-Pedidos && git pull --ff-only
cd /opt/farmacias-red-comparador
docker compose -f docker-compose.prod.yml up -d --build pedidos
curl -I https://pedidos.farmaciasred.com/login   # esperado: 200
```

La base y los archivos de datos viven en el volumen (`/data` del contenedor):
un rebuild NO los toca. Backups de la base en `/root/backups-pedidos/` del VPS.

## Migración de datos desde PythonAnywhere

La cuenta gratuita no tiene SSH; los archivos se bajan desde la web.

1. En PythonAnywhere → pestaña **Files** → carpeta del proyecto:
   - Descargar `pedidos.db` (la base con todos los pedidos).
   - Descargar el contenido de `data/` (presupuesto.csv, precios_dds.xlsx,
     precios_suizo_cmp.xlsx, etc.).
   - Conviene abrir una consola Bash ahí y hacer
     `zip -r backup.zip pedidos.db data/` para bajar un solo archivo.
   - **Antes de bajar la base**: avisar que no se carguen pedidos durante la
     ventana de migración (cualquier pedido creado después de la copia se
     pierde).

2. Subir al VPS y copiar al volumen del contenedor:

```bash
scp backup.zip usuario@VPS:/tmp/
ssh usuario@VPS
cd /tmp && unzip backup.zip

cd /opt/farmacias-red-comparador
# el volumen esta montado en /data del contenedor pedidos
docker compose -f docker-compose.prod.yml cp /tmp/pedidos.db pedidos:/data/pedidos.db
docker compose -f docker-compose.prod.yml exec pedidos mkdir -p /data/archivos
for f in /tmp/data/*; do
  docker compose -f docker-compose.prod.yml cp "$f" pedidos:/data/archivos/
done
docker compose -f docker-compose.prod.yml restart pedidos
```

3. Verificar logueándose en https://pedidos.farmaciasred.com con un usuario
   real: deben verse los pedidos históricos y el catálogo de productos.

## Cutover

1. Comunicar la URL nueva a las 22 sucursales (y actualizar cualquier acceso
   directo guardado).
2. En PythonAnywhere: reemplazar la app por una página estática que diga
   "Nos mudamos a https://pedidos.farmaciasred.com" (o directamente
   deshabilitar la web app).
3. Dejar la cuenta de PythonAnywhere intacta 1-2 semanas como respaldo de los
   archivos, después limpiar.

## Backups (importante)

`pedidos.db` queda en el volumen Docker `pedidos_data`. El cron de backup del
host (`scripts/backup_db.sh` del comparador) solo respalda Postgres — hay que
agregar el respaldo del volumen. Opción simple, sumar al cron diario:

```bash
docker compose -f /opt/farmacias-red-comparador/docker-compose.prod.yml \
  cp pedidos:/data/pedidos.db /opt/farmacias-red-comparador/backups/daily/pedidos_$(date +%Y%m%d).db
```

(SQLite admite copiar el archivo mientras la app corre con riesgo mínimo a
este volumen de escrituras; si se quiere perfecto, usar
`sqlite3 /data/pedidos.db ".backup /data/backup_pedidos.db"` dentro del
contenedor y copiar ese.)

## Rollback

Si algo falla después del cutover: reactivar la web app de PythonAnywhere
(sigue teniendo la base al momento de la copia) y volver a avisar la URL
vieja. Nada del stack del comparador se toca en el rollback:
`docker compose -f docker-compose.prod.yml stop pedidos` y listo.

## Después de la migración (destrabado por estar en el VPS)

- App-Pedidos puede leer `precios_snapshot` del Postgres del comparador por la
  red interna de Docker (chau XLSX manuales).
- App-Pedidos puede leer ventas/stock/catálogo del Supabase de BI con un rol
  de solo lectura (chau CSV Presupuesto manual).
- Integración del stock del CD (base externa, requiere matching de productos).
