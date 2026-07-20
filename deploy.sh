#!/usr/bin/env bash
#
# Deploy de App-Pedidos a producción (VPS Docker).
#
# Corre DESDE tu máquina local: se conecta por SSH al VPS, trae lo último de
# GitHub dentro de /opt/App-Pedidos, reconstruye el contenedor `pedidos` y
# verifica que quede sano. No pisa la base ni los datos del VPS (están fuera
# del repo, ver COMO_TRABAJAR.md).
#
# Uso:
#   ./deploy.sh
#
# Requisitos:
#   - Acceso SSH por clave al VPS (sin password interactivo).
#   - Los cambios ya pusheados a origin/main (este script NO pushea).
#
set -euo pipefail

# --- Config del VPS -----------------------------------------------------------
SSH_HOST="root@179.43.123.251"
SSH_PORT="5930"
APP_DIR="/opt/App-Pedidos"                 # repo que se actualiza con git pull
COMPOSE_DIR="/opt/farmacias-red-comparador" # desde acá se corre docker compose
COMPOSE_FILE="docker-compose.prod.yml"
SERVICE="pedidos"
CONTAINER="farmacias-red-comparador-pedidos-1"
HEALTH_URL="https://pedidos.farmaciasred.com/"

SSH=(ssh -p "$SSH_PORT" -o BatchMode=yes -o ConnectTimeout=20 "$SSH_HOST")

echo "==> [1/4] Commit actual en el VPS"
"${SSH[@]}" "cd $APP_DIR && git rev-parse --short HEAD && git log --oneline -1"

echo
echo "==> [2/4] git pull --ff-only en $APP_DIR"
"${SSH[@]}" "cd $APP_DIR && git pull --ff-only"

echo
echo "==> [3/4] Rebuild y levantar el servicio '$SERVICE'"
"${SSH[@]}" "cd $COMPOSE_DIR && docker compose -f $COMPOSE_FILE up -d --build $SERVICE"

echo
echo "==> [4/4] Verificación"
"${SSH[@]}" "docker ps --filter name=$SERVICE --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'"
echo "-- último commit desplegado --"
"${SSH[@]}" "cd $APP_DIR && git rev-parse --short HEAD"
echo "-- health check HTTP --"
code=$(curl -s -o /dev/null -w '%{http_code}' "$HEALTH_URL" || echo "000")
echo "$HEALTH_URL -> HTTP $code"
case "$code" in
  200|302) echo "OK: producción responde." ;;
  *) echo "ATENCIÓN: código inesperado ($code). Revisá los logs:"
     echo "  ${SSH[*]} \"docker logs --tail 40 $CONTAINER\"" ;;
esac

echo
echo "Deploy terminado."
