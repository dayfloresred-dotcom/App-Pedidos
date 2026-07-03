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
  estados de carga). **Sin cambiar flujos** de pantallas ni endpoints.
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
  confirmaciones a modal; toasts al completar acciones. El
  `location.reload()` tras cada acción SE MANTIENE (fase 2 explícitamente
  fuera de alcance).
- **actualizar_datos**: lista de archivos como tarjetas con fecha y estado.

## Responsive

- Navbar colapsable (hamburguesa Bootstrap) en `< 992px`.
- Pantallas de sucursal en `< 576px`: tablas con scroll horizontal contenido
  en su tarjeta (`overflow-x: auto`), botonera apilada, inputs táctiles
  (min 40px de alto), metric-cards de confirmado apiladas.
- Pantallas de admin (consolidado, generar orden): desktop-first; en móvil
  scroll horizontal aceptable, sin optimización especial.

## Qué NO cambia

- Endpoints, lógica de negocio JS, flujos de pantallas.
- `location.reload()` tras acciones en generar_orden (fase 2 futura).
- Bootstrap 5 CDN sigue siendo la base.
- El backend no se toca en absoluto.

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

- Regresión visual/JS en generar_orden (la pantalla más densa): mitigado
  porque la lógica no se toca y las conversiones `confirm→confirmar` son
  mecánicas; verificación manual pantalla por pantalla antes de deploy.
- Google Fonts requiere internet en el cliente: fallback `system-ui` cubre
  el caso sin red externa.
