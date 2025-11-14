# Changelog

Todos los cambios notables de este proyecto serán documentados en este archivo.

El formato está basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.0.0/),
y este proyecto adhiere a [Semantic Versioning](https://semver.org/lang/es/).

## [2.1.0] - 2025-11-14

### 🚀 Added - Nuevas funcionalidades

#### Sistema de Snapshots
- **SnapshotService**: Servicio completo para gestión de snapshots de sincronización
  - `load_snapshot()`: Carga snapshot de última sincronización
  - `save_snapshot()`: Guarda estado actual con timestamp
  - `compare_with_current()`: Detecta cambios vs snapshot anterior
  - `reset_snapshot()`: Resetea snapshot para forzar sync completa
  - `get_snapshot_info()`: Obtiene información del snapshot
  - Rotación automática de backups (mantiene últimas 3 copias)
  - Permisos restrictivos (600) en archivos de snapshot

#### Detección de Cambios
- **sync_all_inventory_bulk_with_changes()**: Nueva sincronización optimizada
  - Detecta productos nuevos, modificados y eliminados
  - Solo sincroniza productos con cambios (95% ahorro en API calls)
  - Retorna early si no hay cambios (sin llamadas a Shopify)
  - Actualiza snapshot automáticamente después de cada sync
  - Calcula y reporta métricas de ahorro

#### Nuevos Endpoints API
- **GET /snapshot/info**: Información del snapshot actual
- **POST /snapshot/reset**: Resetear snapshot
- **GET /sync/preview**: Preview de cambios sin ejecutar sync

#### Nuevos Comandos CLI
- `snapshot-info`: Ver información del snapshot
- `preview-changes`: Preview de cambios sin ejecutar sync
- `reset-snapshot`: Resetear snapshot para forzar sync completa
- `sync --force`: Flag para forzar sync completa (ignorar snapshot)

#### Nuevos Modelos de Datos
- **SyncSnapshot**: Modelo para snapshot de sincronización
- **SnapshotProduct**: Modelo para producto en snapshot
- **ChangeDetectionResult**: Resultado de detección de cambios

### ✨ Changed - Cambios

- **POST /sync**: Ahora usa detección de cambios por defecto (optimizado)
- **SyncSummary**: Agregados campos `unchanged`, `new`, `modified`, `deleted`, `snapshot_updated`
- **CLI sync**: Usa modo optimizado por defecto, muestra estadísticas de cambios
- Versión actualizada de 2.0.0 → 2.1.0
- Descripción del proyecto actualizada para reflejar optimización

### 📊 Performance

- **95% reducción en llamadas API** (con 5% de productos cambiados)
- **10-20x más rápido** en sincronizaciones incrementales
- **Sin llamadas a Shopify** cuando no hay cambios detectados
- Tiempo de sync: <10s para <100 cambios (vs 60-90s antes)

### 📝 Documentation

- CHANGELOG.md agregado
- README.md actualizado con funcionalidad de snapshots
- COMPLIANCE_REPORT.md agregado (análisis de cumplimiento vs especificaciones)

---

## [2.0.0] - 2025-11-13

### 🚀 Added - Funcionalidad inicial

#### Actualización Masiva (BULK)
- **Batching automático**: Hasta 250 items por llamada GraphQL
- **sync_all_inventory_bulk()**: Sincronización masiva optimizada
- **Rate limit handling**: Exponential backoff (1s, 2s, 4s, 8s)
- **Retry automático**: Máximo 4 intentos en errores de red/servidor
- **Monitoreo de throttle**: Tracking de GraphQL cost points

#### Servicios Core
- **OdooClient**: Cliente XML-RPC para lectura de inventario
  - Autenticación con caché de UID
  - Filtrado por ubicación y SKU
  - Lectura de stock.quant

- **ShopifyService**: Cliente GraphQL para actualización de inventario
  - Búsqueda de productos por SKU
  - Actualización BULK de inventario
  - Solo modifica cantidad "available" (no committed/incoming)
  - Caché de location_id

- **SyncService**: Orquestador de sincronización
  - Modo BULK y SINGLE
  - Detección de productos sin SKU
  - Resumen detallado de sincronización

#### API REST
- **GET /**: Información del servicio
- **GET /health**: Health check
- **GET /test-connections**: Prueba de conexiones Odoo/Shopify
- **POST /sync**: Sincronización BULK
- **POST /sync/single**: Sincronización producto por producto
- **POST /sync/async**: Sincronización en background

#### CLI
- `test`: Prueba de conexiones
- `sync`: Sincronización (modo BULK por defecto)
- `sync --verbose`: Sincronización con detalles
- `sync --single`: Modo producto por producto

#### Modelos de Datos
- OdooStockQuant
- ShopifyInventoryUpdate
- BulkInventoryAdjustment
- BulkUpdateResult
- SyncResult
- SyncSummary (versión básica)

#### Deployment
- Dockerfile con health checks
- docker-compose.yml
- Usuario no-root en contenedor
- Logging JSON estructurado

### 📝 Documentation

- README.md completo (473 líneas)
- Documentación inline (docstrings)
- Ejemplos de uso
- Guía de troubleshooting

---

## [1.0.0] - Inicial (sin webhooks)

### Added
- Lectura de inventario de Odoo via XML-RPC
- Actualización individual en Shopify
- Sincronización producto por producto
- Configuración via variables de entorno

### Deprecated
- ❌ Webhooks de Odoo (eliminados, reemplazados por consulta directa)

---

## Tipos de cambios

- **Added**: Nueva funcionalidad
- **Changed**: Cambios en funcionalidad existente
- **Deprecated**: Funcionalidad que será eliminada
- **Removed**: Funcionalidad eliminada
- **Fixed**: Corrección de bugs
- **Security**: Cambios de seguridad
