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

- Producción se está mudando de **PythonAnywhere** al **VPS** (Docker),
  en `pedidos.farmaciasred.com`.
- En el VPS el deploy es: `git pull` dentro de `/opt/App-Pedidos` + reinicio del
  contenedor. Eso lo maneja quien tenga acceso SSH (coordinar con Ezequiel).
- Mientras siga PythonAnywhere: `cd App-Pedidos && git pull` → pestaña **Web** → **Reload**.

## Si aparece un conflicto
- Si GitHub Desktop dice que no puede hacer *Pull/Push* por cambios encontrados,
  **no toques nada** y pedí ayuda (Claude o el otro colaborador) para resolverlo.

## Pendiente de seguridad (importante)
- Rotar la contraseña de aplicación de Gmail (quedó expuesta en el historial del
  repo) y cargar las variables de entorno (`MAIL_*`, `SECRET_KEY`) en el VPS.
  Sin esto no salen los mails y las sesiones se caen en cada reinicio.

## Cosas que NO se suben al repo (ya ignoradas)
- `pedidos.db` (base de datos), `*.pkl` (cache), archivos de datos subidos.
  Cada entorno (local / producción) tiene los suyos.
