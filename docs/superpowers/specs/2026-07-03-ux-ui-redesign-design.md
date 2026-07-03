# Rediseño UX/UI del portal App-Pedidos — Diseño aprobado

Fecha: 2026-07-03
Rama: `ui-redesign` (sobre `deploy-vps`)

## Contexto

El portal (Flask + Bootstrap 5 CDN + JS vanilla, corriendo en
pedidos.farmaciasred.com) es funcional pero se siente prototipo: `style.css`
de 13 líneas, fondo taupe saturado (#D3C4B4), botones negros, ~40 colores
hardcodeados inline en los templates, `alert()`/`confirm()` nativos del
navegador para toda interacción, y sin tratamiento móvil.

Decisiones tomadas con el usuario (2026-07-03):

- **Alcance**: rediseño visual completo + micro-UX (toasts, confirmaciones,
  estados de carga) + **eliminación del `location.reload()`** en
  generar_orden y confirmado vía re-render de fragmento server-side
  (ampliación pedida por el usuario el 2026-07-03). Los flujos de pantallas
  y los endpoints de acciones existentes no cambian.
- **Prioridad**: todas las pantallas por igual (sistema de diseño coherente).
- **Paleta**: terracota refinada (respeta la dirección estética elegida por
  Day, el creador del sistema). Se evaluó y descartó por ahora la paleta
  institucional roja (#E60023, la del comparador); la arquitectura de
  variables CSS deja ese tema a un paso si se quiere unificar el ecosistema.
- **Dispositivos**: desktop primero; pantallas de sucursal usables en celular.
- **Enfoque**: sistema de diseño propio SOBRE Bootstrap 5 (opción A). Sin
  temas prefabricados, sin build step, sin dependencias nuevas más allá de
  un `<link>` a Google Fonts.

## Tokens de diseño (variables CSS en `:root`)

| Token | Valor | Uso |
|---|---|---|
| `--brand` | `#8E4F44` | Navbar, botón primario, links de pedido |
| `--brand-hover` | `#74392F` | Hover de acciones primarias |
| `--brand-tint` | `#F3E3DE` | Fondos suaves de acento |
| `--fondo` | `#F6F1EA` | Fondo de página (lino cálido) |
| `--tarjeta` | `#FFFFFF` | Superficie de tarjetas |
| `--tarjeta-head` | `#FBF8F3` | Cabeceras de tabla/tarjeta |
| `--borde` | `#E8DFD3` | Bordes de tarjetas e inputs |
| `--texto` | `#2B2622` | Texto principal |
| `--texto-sec` | `#6E655B` | Texto secundario |
| `--texto-suave` | `#8A7E72` | Cabeceras de tabla, hints |
| Estado pendiente | bg `#FCF3D9` / texto `#8A6116` | Badge |
| Estado comprado | bg `#E3F1E7` / texto `#20603B` | Badge |
| Estado cancelado | bg `#FBE9E6` / texto `#A3372B` | Badge |
| Estado generado | bg `#FDF0E4` / texto `#9A4E12` | Badge (pedido generado) |
| Droguería CD | bg `#E3F1E7` / texto `#1D6B3E` | Badge píldora |
| Droguería SUD | bg `#F8EBD4` / texto `#8A5A12` | Badge píldora |
| Droguería SUIZO | bg `#EFEAFB` / texto `#5B34B5` | Badge píldora |
| Rotación | bg `#E4F0F6` / texto `#155E75` | Badge píldora |

Se mantiene el código de color que los usuarios ya aprendieron (CD verde,
SUD ámbar, SUIZO violeta); solo se armonizan los tonos.

**Tipografía**: Inter 400/500/600/700 vía Google Fonts, fallback
`system-ui`. Cabeceras de tabla: 10.5-11px, peso 600, mayúsculas con
letter-spacing.

## Arquitectura de archivos

1. **`static/style.css`** (~350 líneas) — todo el sistema:
   tokens, reset suave, navbar, tarjetas (`.card` refinada), tablas
   (`.tabla-sistema`: cabecera tint, hover de fila, bordes suaves), badges
   (`.badge-estado-*`, `.badge-drog-*`), botones (`.btn-brand`,
   `.btn-suave`), formularios, `.filter-bar`, toasts, modal de confirmación,
   media queries. **Regla: ningún hex nuevo en templates.**
2. **`static/ui.js`** (~120 líneas, nuevo) — API global:
   - `toast(mensaje, tipo)` — tipo: `exito | error | info`; contenedor
     fijo abajo-derecha, autodismiss 3.5 s, apilables.
   - `confirmar(mensaje, opciones)` — devuelve `Promise<boolean>`; modal
     Bootstrap propio, botón de acción destructiva en rojo, título opcional.
   - `setLoading(boton, estado)` — spinner + `disabled` durante fetch;
     evita dobles clicks (hoy se puede duplicar un envío clickeando 2 veces).
3. **`templates/base.html`** — `<link>` Inter, navbar nueva (círculo "FR" +
   marca "Farmacias Red · Pedidos" + links píldora con estado activo + chip
   de usuario con iniciales + botón salir), colapsable con hamburguesa en
   móvil, contenedor de toasts, `<script src=ui.js>`. Se elimina el
   `<style>` inline.
4. **Templates** (los 7) — reemplazo mecánico, sin tocar lógica:
   - estilos inline → clases del sistema;
   - `alert(...)` → `toast(...)`;
   - `confirm(...)` → `const ok = await confirmar(...)` (las funciones que
     los usan ya son `async` o se convierten trivialmente);
   - botones de acciones fetch → `setLoading()`.
5. **`login.html`** — tarjeta centrada sobre `--fondo` con círculo FR,
   título, inputs grandes, botón primario ancho.

## Detalle por pantalla

- **nueva_solicitud**: filter-bar en tarjeta; tabla de resultados del
  sistema; contador "Ver solicitud (N)" como botón primario con badge;
  modal de revisión ya existente restilado.
- **mis_pedidos**: tabla del sistema; números de pedido en `--brand`;
  badges de estado nuevos; filtro de sucursal en filter-bar.
- **confirmado**: tarjetas de resumen (número/fechas) como metric-cards;
  tabla de ítems con badges de estado, enviado y origen; botones de
  cancelar/restaurar con confirmación modal.
- **consolidado**: metric-cards de totales; dos tarjetas (productos /
  detalle por sucursal) con cabecera tint; fila seleccionada resaltada
  con `--brand-tint`.
- **generar_orden**: tarjetas por droguería con cabecera del color de la
  droguería (tokens, no inline); pills de detalle por sucursal con inputs
  más grandes; botones Enviar/Rotación con `setLoading`; todas las
  confirmaciones a modal; toasts al completar acciones. **Sin
  `location.reload()`**: ver "Refresco por fragmento" abajo.
- **actualizar_datos**: lista de archivos como tarjetas con fecha y estado.

## Refresco por fragmento (reemplazo del location.reload)

Filosofía HTMX (la del comparador) sin agregar HTMX — la lógica de qué se
muestra queda 100 % en el servidor, nunca duplicada en JS:

1. **Backend**: extraer el armado de la orden de la vista `generar_orden()`
   a una función `_armar_orden(filtro_suc)` compartida. Ruta nueva
   `GET /generar-orden/fragmento?suc=...` (admin) que renderiza solo el
   partial de la grilla. Los endpoints de acciones (`/api/orden/*`) no
   cambian.
2. **Template**: la grilla de tarjetas de `generar_orden.html` se extrae al
   partial `templates/_orden_grid.html`, incluido con `{% include %}` en la
   página completa y renderizado solo por la ruta de fragmento.
3. **JS** (`refrescarOrden()` en generar_orden): tras cada acción exitosa,
   `fetch` del fragmento y swap de `innerHTML` del contenedor,
   **preservando**: (a) posición de scroll de la página y de cada
   card-body, (b) qué filas de detalle estaban expandidas (por
   `data-rid`), (c) el filtro de sucursal activo y la selección del
   dropdown de export. Toast de éxito al completar; en error, toast de
   error sin swap.
4. **confirmado.html**: mismo patrón liviano — cancelar/restaurar ítem
   refresca la tabla de ítems vía fragmento `_confirmado_items.html` (o,
   si el costo/beneficio no cierra durante la implementación, mantiene el
   reload: es una página liviana; decisión delegada al plan con preferencia
   por el fragmento).

**Índices SQLite** (van de la mano: sin ellos cada re-render paga el N+1
completo): en `init_db()`, `CREATE INDEX IF NOT EXISTS` sobre
`items_solicitud(sku)`, `items_solicitud(solicitud_id)`,
`envios(sucursal, sku)` y `omitidos(sucursal, sku)`. Cambio aditivo, cero
comportamiento nuevo.

## Responsive

- Navbar colapsable (hamburguesa Bootstrap) en `< 992px`.
- Pantallas de sucursal en `< 576px`: tablas con scroll horizontal contenido
  en su tarjeta (`overflow-x: auto`), botonera apilada, inputs táctiles
  (min 40px de alto), metric-cards de confirmado apiladas.
- Pantallas de admin (consolidado, generar orden): desktop-first; en móvil
  scroll horizontal aceptable, sin optimización especial.

## Qué NO cambia

- Los endpoints de acciones existentes (`/api/orden/*`, `/api/item/*`,
  exports) y su lógica de negocio.
- Los flujos de pantallas (mismas pantallas, mismos pasos).
- Bootstrap 5 CDN sigue siendo la base.
- Backend: solo se agregan la ruta de fragmento, el refactor
  `_armar_orden()` y los índices; nada del modelo de datos ni de los
  estados cambia.

## Verificación y deploy

1. Prueba local con el venv del scratchpad (`flask` test run): recorrer las
   7 pantallas como admin y como sucursal; probar toasts, confirmaciones y
   loading en las acciones de generar_orden.
2. Deploy al VPS con el procedimiento quirúrgico ya probado: `git archive`
   → `/opt/App-Pedidos` → `docker compose up -d --build pedidos`. El
   comparador no se toca; PythonAnywhere no se entera.
3. Revisión del usuario en pedidos.farmaciasred.com con datos reales; luego
   mostrar a Day antes de considerar merge a main.

## Riesgos

- Regresión en generar_orden (la pantalla más densa) por el refresco de
  fragmento: riesgo moderado. Mitigación: la lógica de negocio queda
  íntegramente server-side (el fragmento reusa el mismo código que la
  página completa), los endpoints de acciones no cambian, y la
  verificación manual se concentra en esa pantalla (enviar, rotación,
  omitir, comprar, inexistente, con y sin filtro de sucursal).
- Estado de UI tras el swap (scroll, detalles expandidos, dropdown export):
  cubierto explícitamente por `refrescarOrden()`; verificar en la prueba
  manual encadenando 3+ acciones seguidas.
- Google Fonts requiere internet en el cliente: fallback `system-ui` cubre
  el caso sin red externa.
