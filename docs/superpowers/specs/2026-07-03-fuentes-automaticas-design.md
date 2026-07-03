# Fuentes automáticas de datos — Diseño aprobado

Fecha: 2026-07-03
Rama: `ui-redesign` (continúa sobre el rediseño ya deployado)

## Contexto y objetivo

Hoy el catálogo de App-Pedidos se alimenta subiendo a mano hasta 6 archivos
en "Actualizar datos" (presupuesto CSV con ventas/stock/troquel, XLSX de
precios exportados del comparador, etc.). Este proyecto reemplaza esa carga
manual por tres fuentes automáticas:

1. **Precios SUD/SUIZO** → Postgres del comparador (red interna de Docker).
2. **Catálogo + ventas + stock por sucursal** → MySQL de Plex (el ERP vivo),
   conexión directa SIN pasar por Supabase (decisión del usuario 2026-07-03:
   datos operativos frescos, sin depender del ETL diario; bonus: Plex tiene
   el troquel que el espejo no tiene).
3. **Stock del CD (centro de distribución)** → MySQL de Quantio (el depósito
   maneja su propia base; credenciales read-only ya disponibles; schema a
   explorar en Fase 0).

La carga manual de archivos QUEDA como fallback. La migración no tiene punto
de no retorno.

## Principio rector

`construir_catalogo()` produce **exactamente la misma estructura** que hoy
arma `load_productos()` desde archivos — la lista de dicts con campos: sku,
ean, descripcion, laboratorio, rubro, stock_cd, drogueria, mejor_precio,
drog_ext, troquel, troquel_pres, necesidad, stock_real, ventas — y escribe
el mismo pickle cache. Ningún consumidor (app.py, exports, fragmentos)
cambia. La lógica de asignación de droguería (CD si hay stock; si no, la
externa más barata; SIN_PRECIO si no hay precio) se **extrae de
data_loader.py a una función compartida** usada por ambos pipelines
(archivos y fuentes) — una sola fuente de verdad.

## Arquitectura

Módulo nuevo `fuentes.py` con:

- `PlexERP` — conector pymysql read-only al MySQL de Plex.
- `ComparadorPrecios` — conector psycopg2 read-only al Postgres del
  comparador.
- `QuantioCD` — conector pymysql read-only al MySQL de Quantio.
- `construir_catalogo()` — orquesta los tres, ensambla la estructura de
  productos, escribe el pickle y refresca el catálogo en memoria.
- Estado por fuente persistido en SQLite (tabla `fuentes_estado`).

## Conector Plex ERP

- Conexión: `PLEX_DB_URL` (env), base `onze_center`, usuario read-only
  existente (el mismo que usa el ETL del dashboard). Timeouts de conexión y
  lectura configurados.
- **Las queries se copian del ETL probado de dashboard-bi (`etl/etl.py`)**,
  no se inventa SQL nuevo contra el ERP de producción:
  - Catálogo: `medicamentos m LEFT JOIN laboratorios l ON l.CodLab=m.CodLab
    LEFT JOIN rubros r ON r.CodRubro=m.CodRubro`, filtrado a rubros
    Perfumería y Accesorios. Campos: IDProducto (sku), descripción,
    laboratorio, rubro, troquel (columna exacta de `medicamentos` a
    confirmar en Fase 0 contra `farmacias-red-comparador/docs/erp_mysql_schema_legacy.md`).
  - EANs: `productoscodebars` (EAN principal por producto; mismo criterio
    que el ETL).
  - Ventas (ventana `VENTAS_VENTANA_DIAS`, default 60): `factlineas fl
    INNER JOIN factcabecera fc ON fc.IDComprobante=fl.IDComprobante`,
    `fc.Tipo IN ('FA','TF','FV','TK','NC')` con **NC restando**, agrupado
    por `fc.Sucursal` e `fl.IDProducto`, `fc.Emision >= hoy - ventana`.
  - Stock por sucursal (en vivo): `stock st` con `st.Sucursal`,
    `st.IDProducto`, `st.Cantidad`.
- Mapeo sucursal → nombre: el dict `SUCURSALES` existente de config.py
  (id numérico → nombre), con las exclusiones vigentes (`EXCLUIR`).
- **Disciplina de producción (obligatoria)**: consultas SOLO durante el
  refresco (cron diario + botón manual); nunca en requests de usuario;
  timeouts; una conexión por refresco, cerrada al terminar.

## Conector comparador (precios)

- Conexión: `COMPARADOR_DB_URL` (env) → `postgres:5432` por la red interna
  de Docker, base `farmacias_red`, con rol read-only nuevo `pedidos_ro`
  (CREATE ROLE + GRANT SELECT sobre `productos` y `precios_snapshot`;
  one-time documentado en el runbook de deploy).
- Join directo por SKU: `productos.sku_erp` = IDProducto de Plex. Sin
  matching por EAN.
- Query: último snapshot por (producto, droguería) —
  `DISTINCT ON (producto_id, drogueria) ... ORDER BY producto_id,
  drogueria, consultado_at DESC` — para droguerías `DDS` y `SUIZO`, tomando
  `precio_con_iva`. **`DDS` se traduce a `SUD`** (nomenclatura de
  App-Pedidos).
- También se trae `productos.cod_alfabeta` → troquel del export `.dds`.
- Guardia de frescura: si el snapshot más reciente tiene más de 48 h, la
  fuente queda en estado amarillo (funciona, con aviso).

## Conector Quantio CD

- Conexión: `CD_MYSQL_URL` (env), usuario read-only ya disponible.
- **Fase 0 — exploración de schema** (primera tarea del plan): script
  read-only que lista tablas y columnas, identifica dónde vive el stock y
  qué identificadores de producto existen (¿EAN? ¿troquel? ¿código
  compartido con Plex?), muestra samples y deja conclusiones en
  `docs/quantio_cd_schema.md`. Las queries concretas del conector se fijan
  con ese resultado.
- Interfaz del conector (independiente del schema): devuelve
  `[{identificadores del producto..., cantidad}]`.
- **Matching en cascada** contra el catálogo de Plex:
  1. Código compartido (si la exploración revela que Quantio usa el mismo
     IDProducto/convención que Plex, la cascada termina acá).
  2. EAN.
  3. Troquel.
  4. Tabla `mapeo_cd` (SQLite): `codigo_quantio → sku`, persistente,
     cargada manualmente.
- Los productos del CD sin match quedan contados en la pantalla de fuentes,
  con **CSV de no-matcheados descargable** y **upload de CSV de mapeos
  confirmados** (columnas: codigo_quantio, sku) que alimenta `mapeo_cd`.
  El esfuerzo manual se hace una vez y persiste.
- Si la fuente Quantio no está configurada o falla y existe archivo manual
  de stock CD, se usa el archivo (fallback vigente).

## Estrategia del troquel

- `troquel_pres` (export Quantio/CD): desde `medicamentos` de Plex (Fase 0
  confirma la columna). Fallback: columna Troquel del CSV manual.
- `troquel` (export .dds/SUD): `cod_alfabeta` del comparador. Fallback:
  parseo del `precios_sud.txt` manual si está subido (lógica actual).

## Refresco: un mecanismo, dos disparadores

- Endpoint `POST /api/fuentes/refrescar`. Autorización: sesión admin **o**
  header `X-Cron-Token` igual a `FUENTES_CRON_TOKEN` (env). Corre EN el
  proceso web (single worker) — así la invalidación del cache en memoria es
  trivial y no hay problemas cross-proceso. Duración esperada: segundos;
  dentro del timeout de gunicorn (120 s).
- **Botón "Actualizar ahora"** en la pantalla (con `setLoading` + toast).
- **Cron del host a las 10:30** (después del ETL de Supabase ~4:00 — solo
  como referencia horaria de baja carga — y de los syncs del comparador
  ~8:30-9:30): `curl -fsS -X POST -H "X-Cron-Token: ..."
  https://pedidos.farmaciasred.com/api/fuentes/refrescar`, instalado como
  cron.d en el VPS (mismo patrón que los crons del comparador).
- **Resiliencia por fuente**: cada conector guarda su último resultado
  exitoso (pickle por fuente con timestamp en `/data`). Si una fuente falla
  en un refresco, el catálogo se ensambla con el último dato bueno de esa
  fuente y el estado queda amarillo/rojo con el error visible. El refresco
  solo falla por completo si una fuente nunca tuvo éxito Y no hay archivo
  fallback para su dato.
- Estado persistido: tabla `fuentes_estado(fuente TEXT PK, ultima_ok TEXT,
  filas INTEGER, error TEXT, actualizado TEXT)`.

## Pantalla "Actualizar datos" renovada

Sección nueva arriba, "Fuentes automáticas":

- Tarjeta por fuente (Plex / Comparador / Quantio CD): última actualización
  OK, filas traídas, estado (verde = fresco, amarillo = con aviso/stale,
  rojo = error con mensaje).
- Botón "Actualizar ahora".
- Bloque CD: contador de no-matcheados + link de descarga CSV + upload de
  mapeos confirmados.

La carga manual de archivos queda debajo, rotulada "Fallback manual".

## Config, dependencias y deploy

- Env vars nuevas (campos separados para evitar problemas de URL-encoding
  en passwords): `PLEX_HOST`, `PLEX_PORT`, `PLEX_USER`, `PLEX_PASSWORD`,
  `PLEX_DB`; `CD_HOST`, `CD_PORT`, `CD_USER`, `CD_PASSWORD`, `CD_DB`;
  `COMPARADOR_DB_URL` (esta sí URL: la genera el deploy en el VPS con el
  rol pedidos_ro, sin caracteres problemáticos); `VENTAS_VENTANA_DIAS`
  (default 60), `FUENTES_CRON_TOKEN`.
- `docker-compose.prod.yml` (repo comparador): pasar las nuevas vars al
  servicio `pedidos` desde el `.env` (`PEDIDOS_*` prefijo en el .env host,
  mapeadas a los nombres internos). `.env.prod.example` actualizado.
- `requirements.txt`: + `pymysql`, + `psycopg2-binary` (primeras
  dependencias nuevas; estándar e inevitables para conexión directa).
- Runbook: CREATE ROLE `pedidos_ro` en el Postgres del comparador + cron.d
  del refresco.
- Credenciales SOLO en el `.env` del VPS. Nunca en el repo.

## Qué NO cambia

- `load_productos()` sigue siendo la puerta única al catálogo; el pickle
  cache y su invalidación funcionan igual.
- La lógica de pedidos, exports, fragmentos y el resto de la UI.
- El pipeline de archivos manuales completo (fallback).
- Supabase y el repo dashboard-bi: fuera de esta integración por completo.

## Testing y criterio de aceptación

- Unit tests (pytest, fixtures existentes): cascada de matching del CD y
  ensamblador `construir_catalogo()` con datos inyectados (sin conexiones
  reales); endpoint de refresco (auth por token y por sesión, estados).
- Validación de conectores: en Fase 0/implementación, correr cada query
  contra la fuente real y **comparar contra los archivos actuales** — el
  criterio de aceptación es que el catálogo construido por fuentes coincida
  con el construido por archivos en los campos clave (misma cantidad de
  productos ±deltas explicables, mismos precios para una muestra, mismas
  ventas/stock para una muestra de sucursales).

## Riesgos

- **Carga sobre el ERP vivo**: mitigada por disciplina (refresco 1-2×/día,
  queries del ETL probado, timeouts). Si Plex sufriera, el cron se puede
  espaciar o mover de horario sin tocar código.
- **Schema Quantio desconocido**: acotado por la Fase 0 y la cascada de
  matching; el peor caso (sin identificadores comunes) degrada a mapeo
  manual asistido por CSV, no bloquea el resto.
- **Deriva de precios comparador vs XLSX**: la validación de aceptación
  compara contra los XLSX actuales antes del switch.
