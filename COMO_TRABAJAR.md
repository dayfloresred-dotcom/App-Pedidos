# Cómo trabajar en App-Pedidos (equipo)

Somos dos (o más) trabajando sobre el mismo repositorio de GitHub
(`dayfloresred-dotcom/App-Pedidos`). Para no pisarnos, seguimos este flujo.

## Regla de oro
**Antes de empezar a cambiar algo, traé lo último.** El otro pudo haber subido cambios.

## Flujo de cambios (con GitHub Desktop)

1. **Traer lo último**
   - GitHub Desktop → **Fetch origin** → **Pull origin**.
   - (Si trabajás con Claude, el `git pull` lo hace Claude al empezar la sesión.)

2. **Hacer los cambios**
   - Editás / se hacen los cambios y quedan *commiteados* (con un mensaje claro).

3. **Subir**
   - GitHub Desktop → **Push origin**.

4. **Avisar**
   - Si el cambio es grande o toca archivos compartidos, avisar al otro para
     que haga *Pull* y no genere conflictos.

## Deploy (publicar en producción)

- Producción es **solo el VPS** (Docker): `pedidos.farmaciasred.com`.
  El cutover se completó el 06/07/2026; PythonAnywhere quedó como redirect
  a la URL nueva (expira el 03/08/2026).
- El deploy es: `git pull` dentro de `/opt/App-Pedidos` + rebuild del
  contenedor. Eso lo maneja quien tenga acceso SSH (coordinar con Ezequiel).
  Detalle completo en `docs/2026-07-02-migracion-vps.md`.
- **Atajo:** desde tu máquina (con acceso SSH por clave al VPS) corré
  `./deploy.sh`. Hace el `git pull`, el rebuild del contenedor `pedidos` y
  verifica que producción responda. Acordate de pushear los cambios a
  `origin/main` antes: el script NO pushea, solo publica lo que ya está en GitHub.

## Si aparece un conflicto
- Si GitHub Desktop dice que no puede hacer *Pull/Push* por cambios encontrados,
  **no toques nada** y pedí ayuda (Claude o el otro colaborador) para resolverlo.

## Pendiente de seguridad (importante)
- Las variables (`MAIL_*`, `SECRET_KEY`) ya están cargadas en el VPS y los
  mails salen (configurado 06/07/2026). Falta SOLO rotar la contraseña de
  aplicación de Gmail (quedó expuesta en el historial del repo): generar una
  nueva en la cuenta de Gmail, revocar la vieja y pasarle el valor nuevo a
  Ezequiel para actualizar el `.env` del VPS.

## Cosas que NO se suben al repo (ya ignoradas)
- `pedidos.db` (base de datos), `*.pkl` (cache), archivos de datos subidos.
  Cada entorno (local / producción) tiene los suyos.
