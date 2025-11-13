# Conector de Stock Odoo-Shopify

Conector unidireccional (Odoo → Shopify) para sincronización de inventario mediante consulta directa a la API de Odoo.

## Descripción

Este conector lee el inventario completo de una ubicación específica en Odoo y sincroniza las cantidades con Shopify. El conector **consulta activamente a Odoo** (modelo pull) en lugar de esperar webhooks.

### Arquitectura

```
┌──────────────┐                    ┌──────────────────┐                    ┌──────────────┐
│              │  XML-RPC           │                  │  GraphQL           │              │
│     Odoo     │ <───────────────── │  Conector API    │ ─────────────────> │   Shopify    │
│  (Fuente)    │  Query Inventory   │  (FastAPI)       │  Update Inventory  │  (Destino)   │
│              │                    │                  │                    │              │
└──────────────┘                    └──────────────────┘                    └──────────────┘
```

### Flujo de Sincronización

1. **Conector** llama a la API XML-RPC de Odoo para leer el inventario de la ubicación 28
2. **Conector** procesa cada producto con SKU
3. **Conector** consulta Shopify GraphQL para obtener el stock actual
4. **Conector** calcula el delta y ajusta el inventario en Shopify

## Características

✅ Consulta directa a Odoo via XML-RPC
✅ Sincronización de ubicación específica (ID: 28)
✅ Búsqueda de productos por SKU
✅ Actualización automática de inventario en Shopify
✅ API REST con endpoints de sincronización
✅ CLI para sincronización desde línea de comandos
✅ Logging detallado de operaciones
✅ Soporte para sincronización en background

## Requisitos

- Python 3.13+
- Acceso a Odoo (usuario y contraseña)
- Cuenta de Shopify con acceso a Admin API

## Instalación

### 1. Clonar el repositorio

```bash
git clone <url-del-repositorio>
cd shopify-odoo-real-conector
```

### 2. Crear entorno virtual

```bash
python -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate
```

### 3. Instalar dependencias

```bash
pip install -e .
```

### 4. Configurar variables de entorno

Copia el archivo de ejemplo y edita con tus credenciales:

```bash
cp .env.example .env
```

Edita `.env` y configura:

```bash
# Odoo
ODOO_URL=https://odoo.tuempresa.com
ODOO_DATABASE=produccion
ODOO_USERNAME=admin@tuempresa.com
ODOO_PASSWORD=tu_password
ODOO_LOCATION_ID=28

# Shopify
SHOPIFY_STORE_URL=https://tu-tienda.myshopify.com
SHOPIFY_ACCESS_TOKEN=shpat_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
SHOPIFY_API_VERSION=2025-10

# Servidor
HOST=0.0.0.0
PORT=8000
LOG_LEVEL=INFO
```

#### Obtener credenciales de Odoo

- **URL**: La URL de tu instancia de Odoo
- **Database**: El nombre de la base de datos (si no sabes cuál es, pregunta al administrador)
- **Username**: Tu usuario de Odoo (generalmente el email)
- **Password**: Tu contraseña de Odoo
- **Location ID**: El ID de la bodega/ubicación (en este caso: 28)

#### Obtener Access Token de Shopify

1. Ve a tu panel de administración de Shopify
2. Navega a **Settings > Apps and sales channels > Develop apps**
3. Crea una nueva app o selecciona una existente
4. En **Configuration**, configura los siguientes permisos:
   - `read_inventory`
   - `write_inventory`
   - `read_products`
5. Instala la app y copia el **Admin API access token**

## Uso

### Opción 1: CLI (Línea de Comandos)

La forma más simple de sincronizar:

```bash
# Probar conexiones con Odoo y Shopify
python -m odoo_shopify_connector.cli test

# Sincronizar inventario
python -m odoo_shopify_connector.cli sync

# Sincronizar con detalles de cada producto
python -m odoo_shopify_connector.cli sync --verbose
```

### Opción 2: API REST

Iniciar el servidor:

```bash
python -m odoo_shopify_connector.main
```

O con uvicorn directamente:

```bash
uvicorn odoo_shopify_connector.api:app --host 0.0.0.0 --port 8000
```

#### Endpoints disponibles:

**GET /**
```bash
curl http://localhost:8000/
```
Información del servicio.

**GET /health**
```bash
curl http://localhost:8000/health
```
Health check.

**GET /test-connections**
```bash
curl http://localhost:8000/test-connections
```
Prueba las conexiones con Odoo y Shopify.

**POST /sync**
```bash
curl -X POST http://localhost:8000/sync
```
Sincroniza todo el inventario (puede tardar dependiendo del número de productos).

**POST /sync/async**
```bash
curl -X POST http://localhost:8000/sync/async
```
Inicia la sincronización en segundo plano (retorna inmediatamente).

### Documentación de la API

FastAPI genera documentación automática:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## Funcionamiento Interno

### Lectura de Inventario de Odoo

El conector usa XML-RPC para consultar el modelo `stock.quant` de Odoo:

```python
# Dominio de búsqueda
domain = [
    ('location_id', '=', 28),          # Ubicación específica
    ('quantity', '>', 0),               # Solo productos con stock
    ('product_id.default_code', '!=', False)  # Solo productos con SKU
]
```

### Sincronización con Shopify

Para cada producto de Odoo:

1. **Busca por SKU** en Shopify usando GraphQL
2. **Obtiene stock actual** de la variante en Shopify
3. **Calcula delta** = cantidad_odoo - cantidad_shopify
4. **Ajusta inventario** con la mutación `inventoryAdjustQuantities`

### Mapeo de Datos

| Campo en Odoo | Campo en Shopify |
|---------------|------------------|
| `product_id.default_code` (SKU) | `variant.sku` |
| `quantity` | `inventoryLevel.quantities.available` |
| `location_id` | - (no se mapea, Shopify usa su propia ubicación) |

## Respuestas de la API

### Sincronización Exitosa

```json
{
  "total_products": 15,
  "successful": 14,
  "failed": 1,
  "skipped": 0,
  "results": [
    {
      "success": true,
      "message": "Stock sincronizado exitosamente para SKU 'PROD-001'",
      "sku": "PROD-001",
      "quantity_updated": 25,
      "delta": 5
    },
    ...
  ]
}
```

### Test de Conexiones

```json
{
  "odoo": {
    "status": "OK",
    "message": "Conexión exitosa. UID: 2"
  },
  "shopify": {
    "status": "OK",
    "message": "Conexión exitosa. Location: gid://shopify/Location/12345"
  },
  "overall": "OK"
}
```

## Programar Sincronización Periódica

### Con cron (Linux)

Edita el crontab:

```bash
crontab -e
```

Agrega una línea para sincronizar cada hora:

```cron
0 * * * * cd /ruta/al/proyecto && /ruta/al/venv/bin/python -m odoo_shopify_connector.cli sync >> /var/log/odoo-shopify-sync.log 2>&1
```

### Con systemd timer (Linux)

Crea `/etc/systemd/system/odoo-shopify-sync.service`:

```ini
[Unit]
Description=Sincronización Odoo-Shopify

[Service]
Type=oneshot
User=www-data
WorkingDirectory=/opt/odoo-shopify-connector
Environment="PATH=/opt/odoo-shopify-connector/venv/bin"
EnvironmentFile=/opt/odoo-shopify-connector/.env
ExecStart=/opt/odoo-shopify-connector/venv/bin/python -m odoo_shopify_connector.cli sync
```

Crea `/etc/systemd/system/odoo-shopify-sync.timer`:

```ini
[Unit]
Description=Sincronización Odoo-Shopify cada hora

[Timer]
OnBootSec=5min
OnUnitActiveSec=1h

[Install]
WantedBy=timers.target
```

Activa el timer:

```bash
sudo systemctl daemon-reload
sudo systemctl enable odoo-shopify-sync.timer
sudo systemctl start odoo-shopify-sync.timer
```

### Con Task Scheduler (Windows)

1. Abre Task Scheduler
2. Crea una nueva tarea básica
3. Configura el trigger (ej: cada hora)
4. Acción: "Iniciar un programa"
5. Programa: `C:\ruta\al\venv\Scripts\python.exe`
6. Argumentos: `-m odoo_shopify_connector.cli sync`
7. Directorio: `C:\ruta\al\proyecto`

## Despliegue con Docker

### Dockerfile

```bash
docker build -t odoo-shopify-connector .
```

### Docker Compose

```bash
docker-compose up -d
```

El contenedor incluye health checks automáticos.

## Troubleshooting

### Error: "Autenticación fallida con Odoo"

**Causas:**
- Credenciales incorrectas
- Nombre de base de datos incorrecto
- Usuario no tiene permisos

**Solución:**
1. Verifica `ODOO_URL`, `ODOO_DATABASE`, `ODOO_USERNAME`, `ODOO_PASSWORD` en `.env`
2. Prueba conectarte manualmente a Odoo con esas credenciales
3. Verifica que el usuario tenga permisos para leer `stock.quant` y `product.product`

### Error: "No se encontraron productos en ubicación 28"

**Causas:**
- La ubicación 28 no existe
- La ubicación está vacía
- Los productos no tienen SKU

**Solución:**
1. Verifica en Odoo que la ubicación 28 existe
2. Consulta qué ubicaciones tienes: En Odoo > Inventario > Configuración > Ubicaciones
3. Actualiza `ODOO_LOCATION_ID` en `.env` si es necesario
4. Asegúrate de que los productos tengan el campo "Referencia interna" (SKU) lleno

### Error: "Producto con SKU 'XXX' no encontrado en Shopify"

**Causas:**
- El SKU en Odoo no coincide con Shopify
- El producto no existe en Shopify

**Solución:**
1. Verifica que el SKU en Odoo sea EXACTAMENTE igual al SKU en Shopify
2. Los SKU son case-sensitive
3. Revisa en Shopify Admin que el producto tenga el SKU configurado

### El stock no se actualiza correctamente

**Causas:**
- Diferencia de unidades (Odoo en kg, Shopify en unidades)
- Múltiples ubicaciones en Shopify

**Solución:**
1. Verifica que las unidades de medida sean consistentes
2. El conector usa la primera ubicación de Shopify
3. Revisa los logs para ver qué delta se está aplicando

## Logs

Los logs incluyen información detallada:

```
2025-01-13 10:30:45 - INFO - Autenticando con Odoo: https://odoo.empresa.com, DB: produccion
2025-01-13 10:30:45 - INFO - Autenticación exitosa. UID: 2
2025-01-13 10:30:45 - INFO - Obteniendo inventario de ubicación 28
2025-01-13 10:30:46 - INFO - Se encontraron 15 registros de stock en ubicación 28
2025-01-13 10:30:46 - INFO - Sincronizando producto: SKU=PROD-001, Cantidad=25.0
2025-01-13 10:30:47 - INFO - Stock actual en Shopify para SKU PROD-001: 20
2025-01-13 10:30:47 - INFO - Ajustando inventario: 20 -> 25 (delta: 5)
2025-01-13 10:30:47 - INFO - Inventario ajustado exitosamente
```

## Limitaciones Conocidas

1. **Solo sincroniza una ubicación**: El conector está configurado para ubicación 28
2. **Solo productos con SKU**: Los productos sin SKU se omiten
3. **Sincronización manual/programada**: No es en tiempo real
4. **Una ubicación en Shopify**: Usa la primera ubicación disponible

## Contribuir

Las contribuciones son bienvenidas. Por favor:

1. Haz fork del repositorio
2. Crea una rama para tu feature (`git checkout -b feature/mi-feature`)
3. Commit tus cambios (`git commit -am 'Agregar nueva funcionalidad'`)
4. Push a la rama (`git push origin feature/mi-feature`)
5. Crea un Pull Request

## Licencia

[Especificar licencia]

## Soporte

Para reportar bugs o solicitar features, por favor abre un issue en el repositorio.
