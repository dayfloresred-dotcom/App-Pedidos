# App Pedidos Farmacias Red — Diseño aprobado
Fecha: 2026-06-08

## Resumen

Aplicación web que permite a las 22 sucursales de Farmacias Red enviar solicitudes de refuerzo de productos de Perfumería y Accesorios. El administrador de compras centraliza las solicitudes, genera las órdenes de compra por droguería y registra la fecha en que efectuó cada pedido.

---

## Arquitectura

- **Backend:** Python Flask + SQLite
- **Frontend:** HTML / CSS / JS vanilla (sin frameworks pesados)
- **Datos de productos:** leídos al inicio desde los archivos CSV existentes en `Necesidad Sucursales/`
- **Despliegue inicial:** local + ngrok para pruebas; luego Railway (cloud gratuito) para producción
- **Autenticación:** sesiones Flask con usuario/contraseña por rol

---

## Roles y acceso

| Rol | Usuario | Pantallas disponibles |
|---|---|---|
| Sucursal | Nombre de la sucursal (ej: CERRO) | Nueva solicitud · Mis pedidos |
| Admin | admin | Nueva solicitud · Mis pedidos · Consolidado · Por sucursal · Generar orden |

En "Nueva solicitud" el admin ve un selector de sucursal al inicio para elegir en nombre de quién crea el pedido. En "Mis pedidos" el admin ve todas las solicitudes de todas las sucursales, con posibilidad de filtrar por sucursal.

Las sucursales no pueden ver ni acceder a las pantallas del admin.

---

## Pantallas

### 1. Login
- Campo: Sucursal / usuario
- Campo: Contraseña
- Botón: Ingresar
- Redirige a la vista correspondiente según rol

### 2. Nueva solicitud (sucursal)
- Barra de búsqueda: Laboratorio (texto con sugerencias) + Buscar producto (texto libre)
- Tabla de resultados: EAN · Producto · Laboratorio · Cantidad (input editable, default 0)
- Botón "Ver solicitud (N)" — muestra los productos con cantidad > 0
- Botón "Confirmar solicitud" — lleva a revisión

### 3. Revisión antes de confirmar (sucursal)
- Tabla resumen con los productos seleccionados y sus cantidades
- Botón "Volver a editar"
- Botón "Confirmar solicitud ✓" — al confirmar:
  - Se genera número de pedido correlativo: SOL-XXXXXX
  - Se registra fecha y hora de la solicitud
  - La fecha de compra queda pendiente

### 4. Pedido confirmado (sucursal)
- Mensaje de confirmación con número SOL-XXXXXX
- Tarjetas con: N° pedido · Fecha solicitud · Fecha de compra (pendiente)
- Tabla con los productos confirmados
- Botón "← Nueva solicitud"

### 5. Mis pedidos (sucursal)
- Historial de todas las solicitudes de esa sucursal
- Columnas: N° Pedido · Fecha solicitud · Productos · Fecha de compra · Estado
- Estados: Pendiente (amarillo) · Pedido realizado (verde)

### 6. Consolidado (admin)
- Filtros: Laboratorio · Sucursal · Droguería
- Métricas: Productos solicitados · Sucursales activas · Unidades totales
- Panel izquierdo: productos más solicitados con droguería recomendada y total de unidades
- Panel derecho: al hacer clic en un producto, muestra qué sucursales lo pidieron y cuánto

### 7. Por sucursal (admin)
- Vista completa de solicitudes filtradas por sucursal
- Mismo formato que el consolidado pero mostrando el detalle de cada solicitud individual

### 8. Generar orden (admin)
- Dos columnas: SUD | SUIZO
- Cada columna muestra sus productos con EAN, nombre, chips de sucursales, cantidad editable y botón eliminar
- Botón "+ Agregar producto" por droguería
- Total de unidades por droguería
- Botón "Exportar SUD" → genera archivo `.dds` con formato fijo: EAN(13) + Troquel(7) + Nombre producto(33, truncado/padded) + Cantidad
- Botón "Exportar SUIZO" → genera archivo `.arg` con formato fijo: EAN(13) + 30 espacios + Cantidad(3 dígitos zero-padded, ej: `004`)
- Ambos archivos se descargan directamente desde el browser para cargarlos en el portal de cada droguería
- El admin puede editar cantidades y agregar/quitar productos antes de exportar
- Al confirmar la orden se registra la "Fecha de compra" en todas las solicitudes involucradas

---

## Modelo de datos (SQLite)

### Tabla `solicitudes`
| Campo | Tipo | Descripción |
|---|---|---|
| id | INTEGER PK | Autoincremental |
| numero | TEXT | SOL-000001 correlativo |
| sucursal | TEXT | Nombre de la sucursal |
| fecha_solicitud | DATETIME | Timestamp de confirmación |
| fecha_compra | DATE | Completada por admin al hacer el pedido |
| estado | TEXT | pendiente / comprado |

### Tabla `items_solicitud`
| Campo | Tipo | Descripción |
|---|---|---|
| id | INTEGER PK | |
| solicitud_id | INTEGER FK | Referencia a solicitudes |
| sku | TEXT | IDProducto |
| ean | TEXT | Código de barras |
| descripcion | TEXT | Nombre del producto |
| laboratorio | TEXT | Laboratorio |
| cantidad | INTEGER | Unidades solicitadas |
| drogueria | TEXT | SUD / SUIZO / vacío |

### Tabla `usuarios`
| Campo | Tipo | Descripción |
|---|---|---|
| id | INTEGER PK | |
| username | TEXT | Nombre de sucursal o "admin" |
| password_hash | TEXT | Contraseña hasheada |
| rol | TEXT | sucursal / admin |

---

## Flujo principal

1. Sucursal inicia sesión → busca productos → agrega cantidades → confirma solicitud → recibe SOL-XXXXXX
2. Admin ve en "Consolidado" todas las solicitudes pendientes con filtros
3. Admin va a "Generar orden" → ajusta cantidades → exporta orden para SUD y SUIZO
4. Al exportar/confirmar la orden, el sistema registra la fecha de compra en todas las solicitudes involucradas → estado cambia a "Pedido realizado"

---

## Datos de productos

Cargados al inicio desde:
- `Presupuesto 04-06-26.csv` — SKU, EAN (provisional), descripción, laboratorio, rubro, stock y ventas por sucursal
- `Listado de Stock 6-4.csv` — EAN correcto (13 dígitos)
- `Stock CD.csv` — stock en centro de distribución
- `precios Sud.txt` + `precios perfu Suizo.xls` + `precios insumos Suizo.xls` — precios por droguería

Solo se muestran productos con Rubro = Perfumería o Accesorios.

---

## Notificaciones por mail

Cada vez que una sucursal confirma una solicitud, el sistema envía automáticamente un mail a la cuenta del administrador con:
- Número de pedido (SOL-XXXXXX)
- Nombre de la sucursal
- Cantidad de productos solicitados
- Lista resumida de productos y cantidades

- **Mail destino (admin):** jenarraigada.red@gmail.com
- **Mail origen (envío):** cuenta Gmail configurada con contraseña de aplicación
- **Librería:** Flask-Mail + smtplib con SMTP de Gmail (TLS)

---

## Contraseñas iniciales

- Cada sucursal: nombre en minúsculas + "123" (ej: CERRO → `cerro123`, CBA SHOPPING → `cbashopping123`)
- Admin: `admin123`
- Todas las contraseñas se guardan hasheadas con Werkzeug y son cambiables desde el sistema

---

## Tecnologías

- Python 3.10+
- Flask + Flask-Login + Werkzeug (hash de contraseñas)
- SQLite (via sqlite3 estándar)
- HTML5 / CSS3 / JavaScript vanilla
- Bootstrap 5 (CDN) para estilos base
- ngrok para exposición local → Railway para producción
