# Schema Quantio CD — base `plexdr`

Total de tablas: 986


## Conclusiones Fase 0 (2026-07-03)

- El CD corre su propio Plex (base plexdr, 986 tablas).
- Tabla de stock: `stock` (IDProducto bigint, IdDeposito, Cantidad) — 34.241 filas, un solo deposito.
- Catalogo propio: `productos` (IDProducto, Codebar, Troquel, Activo) — 157.618 filas.
- IDProducto con formato identico al CodPlex del Plex central: cascada codigo-directo primero, EAN/troquel de respaldo.
- QUERY_STOCK: JOIN stock+productos con Cantidad > 0.

## Tablas candidatas (detalle)

### `depositos`

| Columna | Tipo |
|---|---|
| IdDeposito | int(11) |
| IdSucursal | int(11) |
| Nombre | varchar(200) |

Filas: 1

- sample 1: `{'IdDeposito': '1', 'IdSucursal': '1', 'Nombre': 'Deposito 1'}`


### `productos`

| Columna | Tipo |
|---|---|
| IDProducto | bigint(20) |
| IDLaboratorio | int(11) |
| IDTamano | int(11) |
| IDRubro | int(11) |
| IDTipoUnidad | int(11) |
| IDTipoConc | int(11) |
| Concentracion | double |
| IDForma | int(11) |
| Troquel | int(11) |
| Codebar | varchar(20) |
| Producto | varchar(100) |
| Presentacion | varchar(50) |
| Unidades | int(11) |
| Importado | char(1) |
| Activo | char(1) |
| Refrigeracion | char(1) |
| Costo | double |
| Margen | double |
| CodAlfabeta | int(11) |
| IDSubRubro | int(11) |
| IDPsicofarmaco | varchar(20) |
| UltimoCosto | double |
| costoPPP | double |
| idProveedor | int(11) |
| idTipoVenta | int(11) |
| idTipoIVA | int(11) |
| gtin | varchar(50) |
| trazable | tinyint(4) |
| IDPerfumeria | int(11) |
| IDActividad | int(11) |
| TipoActualCosto | char(1) |
| idOrigenCosto | int(11) |
| MargenPVP | double |
| vencimiento | tinyint(4) |
| CantidadBulto | int(11) |
| IDClasificador | int(11) |
| logistico | tinyint(4) |
| selectivo | tinyint(4) |
| aerosol | tinyint(4) |
| NoDispOnLine | tinyint(4) |
| DescLaboratorio | double |
| FechaModificacion | datetime |
| idMarca | int(11) |
| ExpendioAutomatizado | tinyint(4) |
| Sector | int(2) |
| Modulo | varchar(1) |
| Fila | int(2) |
| Posicion | int(3) |
| PercepcionIva | tinyint(4) |
| FechaUltimoPrecio | date |
| UltimoPrecio | double |
| ProdPres | varchar(150) |
| FechaPublicacion | datetime |
| visible | tinyint(4) |
| abc | char(1) |
| Ubicacion | varchar(50) |
| IdProductoRegulador | bigint(20) |
| PrecioRegulado | double |
| IdProductoPadre | bigint(20) |
| UnidadesPadre | int(11) |
| TipoPrecioPadre | varchar(1) |
| PorcExtraPrecioPadre | double |
| FechaUbicacion | datetime |
| idItem | int(11) |
| actualizacion_propia | tinyint(4) |
| Fecha_actualizacion_propia_off | datetime |
| FechaModificacionDatosPlex | datetime |
| MantieneMargen | tinyint(4) |
| MantieneMargenPVP | tinyint(4) |

Filas: 157618

- sample 1: `{'IDProducto': '1000100000', 'IDLaboratorio': '1', 'IDTamano': '1', 'IDRubro': '1', 'IDTipoUnidad': '5', 'IDTipoConc': '3', 'Concentracion': '25.0', 'IDForma': '54', 'Troquel': '4564271', 'Codebar': '7790440536414', 'Producto': 'ZOLEPTIL', 'Presentacion': '25 mg comp.x 10', 'Unidades': '10', 'Importado': 'S', 'Activo': 'X', 'Refrigeracion': 'N', 'Costo': '8.19', 'Margen': '0.0', 'CodAlfabeta': '31247', 'IDSubRubro': None, 'IDPsicofarmaco': None, 'UltimoCosto': '0.0', 'costoPPP': '0.0', 'idProveedor': None, 'idTipoVenta': '3', 'idTipoIVA': '1', 'gtin': None, 'trazable': '0', 'IDPerfumeria': None, 'IDActividad': None, 'TipoActualCosto': None, 'idOrigenCosto': '1', 'MargenPVP': '0.0', 'vencimiento': '0', 'CantidadBulto': '0', 'IDClasificador': None, 'logistico': '0', 'selectivo': '0', 'aerosol': '0', 'NoDispOnLine': '0', 'DescLaboratorio': None, 'FechaModificacion': '2019-03-12 16:32:20', 'idMarca': None, 'ExpendioAutomatizado': '0', 'Sector': None, 'Modulo': None, 'Fila': None, 'Posicion': None, 'PercepcionIva': '0', 'FechaUltimoPrecio': '2005-07-01', 'UltimoPrecio': '8.19', 'ProdPres': 'ZOLEPTIL 25 mg comp.x 10', 'FechaPublicacion': None, 'visible': '1', 'abc': None, 'Ubicacion': None, 'IdProductoRegulador': None, 'PrecioRegulado': '0.0', 'IdProductoPadre': None, 'UnidadesPadre': '0', 'TipoPrecioPadre': None, 'PorcExtraPrecioPadre': None, 'FechaUbicacion': None, 'idItem': None, 'actualizacion_propia': '0', 'Fecha_actualizacion_propia_off': None, 'FechaModificacionDatosPlex': None, 'MantieneMargen': '0', 'MantieneMargenPVP': '0'}`
- sample 2: `{'IDProducto': '1000100001', 'IDLaboratorio': '1', 'IDTamano': '1', 'IDRubro': '1', 'IDTipoUnidad': '5', 'IDTipoConc': '3', 'Concentracion': '50.0', 'IDForma': '54', 'Troquel': '4564433', 'Codebar': '7790440536537', 'Producto': 'ZOLEPTIL', 'Presentacion': '50 mg comp.x 30', 'Unidades': '30', 'Importado': 'S', 'Activo': 'X', 'Refrigeracion': 'N', 'Costo': '42.51', 'Margen': '0.0', 'CodAlfabeta': '31248', 'IDSubRubro': None, 'IDPsicofarmaco': None, 'UltimoCosto': '0.0', 'costoPPP': '0.0', 'idProveedor': None, 'idTipoVenta': '3', 'idTipoIVA': '1', 'gtin': None, 'trazable': '0', 'IDPerfumeria': None, 'IDActividad': None, 'TipoActualCosto': None, 'idOrigenCosto': '1', 'MargenPVP': '0.0', 'vencimiento': '0', 'CantidadBulto': '0', 'IDClasificador': None, 'logistico': '0', 'selectivo': '0', 'aerosol': '0', 'NoDispOnLine': '0', 'DescLaboratorio': None, 'FechaModificacion': '2019-03-12 16:32:20', 'idMarca': None, 'ExpendioAutomatizado': '0', 'Sector': None, 'Modulo': None, 'Fila': None, 'Posicion': None, 'PercepcionIva': '0', 'FechaUltimoPrecio': '2005-07-01', 'UltimoPrecio': '42.51', 'ProdPres': 'ZOLEPTIL 50 mg comp.x 30', 'FechaPublicacion': None, 'visible': '1', 'abc': None, 'Ubicacion': None, 'IdProductoRegulador': None, 'PrecioRegulado': '0.0', 'IdProductoPadre': None, 'UnidadesPadre': '0', 'TipoPrecioPadre': None, 'PorcExtraPrecioPadre': None, 'FechaUbicacion': None, 'idItem': None, 'actualizacion_propia': '0', 'Fecha_actualizacion_propia_off': None, 'FechaModificacionDatosPlex': None, 'MantieneMargen': '0', 'MantieneMargenPVP': '0'}`
- sample 3: `{'IDProducto': '1000100002', 'IDLaboratorio': '1', 'IDTamano': '1', 'IDRubro': '1', 'IDTipoUnidad': '5', 'IDTipoConc': '3', 'Concentracion': '100.0', 'IDForma': '54', 'Troquel': '4564353', 'Codebar': '7790440536636', 'Producto': 'ZOLEPTIL', 'Presentacion': '100 mg comp.x 30', 'Unidades': '30', 'Importado': 'S', 'Activo': 'X', 'Refrigeracion': 'N', 'Costo': '70.06', 'Margen': '0.0', 'CodAlfabeta': '31249', 'IDSubRubro': None, 'IDPsicofarmaco': None, 'UltimoCosto': '0.0', 'costoPPP': '0.0', 'idProveedor': None, 'idTipoVenta': '3', 'idTipoIVA': '1', 'gtin': None, 'trazable': '0', 'IDPerfumeria': None, 'IDActividad': None, 'TipoActualCosto': None, 'idOrigenCosto': '1', 'MargenPVP': '0.0', 'vencimiento': '0', 'CantidadBulto': '0', 'IDClasificador': None, 'logistico': '0', 'selectivo': '0', 'aerosol': '0', 'NoDispOnLine': '0', 'DescLaboratorio': None, 'FechaModificacion': '2019-03-12 16:32:20', 'idMarca': None, 'ExpendioAutomatizado': '0', 'Sector': None, 'Modulo': None, 'Fila': None, 'Posicion': None, 'PercepcionIva': '0', 'FechaUltimoPrecio': '2005-07-01', 'UltimoPrecio': '70.06', 'ProdPres': 'ZOLEPTIL 100 mg comp.x 30', 'FechaPublicacion': None, 'visible': '1', 'abc': None, 'Ubicacion': None, 'IdProductoRegulador': None, 'PrecioRegulado': '0.0', 'IdProductoPadre': None, 'UnidadesPadre': '0', 'TipoPrecioPadre': None, 'PorcExtraPrecioPadre': None, 'FechaUbicacion': None, 'idItem': None, 'actualizacion_propia': '0', 'Fecha_actualizacion_propia_off': None, 'FechaModificacionDatosPlex': None, 'MantieneMargen': '0', 'MantieneMargenPVP': '0'}`


### `productoscodebars`

| Columna | Tipo |
|---|---|
| IDProducto | bigint(20) |
| codebar | varchar(20) |
| Origen | char(1) |

Filas: 172710

- sample 1: `{'IDProducto': '0', 'codebar': '', 'Origen': 'D'}`
- sample 2: `{'IDProducto': '0', 'codebar': '1,84111E+13', 'Origen': 'A'}`
- sample 3: `{'IDProducto': '0', 'codebar': '1,8434E+13', 'Origen': 'A'}`


### `stock`

| Columna | Tipo |
|---|---|
| IDProducto | bigint(20) |
| IdDeposito | int(11) |
| Cantidad | int(11) |
| Unidades | int(11) |
| Minimo | int(11) |
| Critico | int(11) |
| maximo | int(11) |

Filas: 34241

- sample 1: `{'IDProducto': '1000100036', 'IdDeposito': '1', 'Cantidad': '3', 'Unidades': '0', 'Minimo': '0', 'Critico': '0', 'maximo': '0'}`
- sample 2: `{'IDProducto': '1000100041', 'IdDeposito': '1', 'Cantidad': '5', 'Unidades': '0', 'Minimo': '0', 'Critico': '0', 'maximo': '0'}`
- sample 3: `{'IDProducto': '1000100042', 'IdDeposito': '1', 'Cantidad': '0', 'Unidades': '0', 'Minimo': '0', 'Critico': '0', 'maximo': '0'}`


### `stockexterno`

| Columna | Tipo |
|---|---|
| IDProducto | bigint(20) |
| Cantidad | int(11) |
| Unidades | int(11) |
| Minimo | int(11) |

Filas: 0



### `stocklotes`

| Columna | Tipo |
|---|---|
| IDLote | int(11) |
| IDProducto | bigint(20) |
| NumeroLote | varchar(20) |
| Serie | varchar(50) |
| PrecioCompra | double |
| FechaVencimiento | datetime |
| Cantidad | int(11) |
| Unidades | int(11) |
| IdDeposito | int(11) |

Filas: 36538

- sample 1: `{'IDLote': '2', 'IDProducto': '1000100036', 'NumeroLote': '1', 'Serie': None, 'PrecioCompra': '52559.33', 'FechaVencimiento': '2027-06-01 00:00:00', 'Cantidad': '3', 'Unidades': '0', 'IdDeposito': '1'}`
- sample 2: `{'IDLote': '3', 'IDProducto': '1000100052', 'NumeroLote': '1', 'Serie': None, 'PrecioCompra': '62280.89', 'FechaVencimiento': '2027-06-01 00:00:00', 'Cantidad': '7', 'Unidades': '0', 'IdDeposito': '1'}`
- sample 3: `{'IDLote': '4', 'IDProducto': '1000100058', 'NumeroLote': '1', 'Serie': None, 'PrecioCompra': '11680.27', 'FechaVencimiento': '2027-06-01 00:00:00', 'Cantidad': '7', 'Unidades': '0', 'IdDeposito': '1'}`


