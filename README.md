# Conector de Stock Odoo-Shopify

Conector unidireccional (Odoo → Shopify) para sincronización de inventario en tiempo real.

## Descripción

Este conector implementa una arquitectura simple basada en webhooks para mantener el inventario de Shopify sincronizado con Odoo. Odoo es la única fuente de verdad, y cada cambio de stock dispara una actualización automática en Shopify.

### Arquitectura

```
┌──────────────┐         ┌──────────────────┐         ┌──────────────┐
│              │  HTTP   │                  │ GraphQL │              │
│     Odoo     │ ──────> │  Conector API    │ ──────> │   Shopify    │
│   (Emisor)   │ POST    │  (FastAPI)       │ Mutation│  (Receptor)  │
│              │         │                  │         │              │
└──────────────┘         └──────────────────┘         └──────────────┘
```

### Flujo de Sincronización

1. **Odoo**: Cuando el stock cambia en `stock.quant`, dispara un webhook HTTP POST
2. **Conector**: Recibe el webhook, valida los datos, y orquesta la actualización
3. **Shopify**: Recibe la mutación GraphQL y ajusta el inventario

## Requisitos

- Python 3.13+
- Cuenta de Shopify con acceso a Admin API
- Odoo con capacidad de configurar Acciones Automatizadas

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
SHOPIFY_STORE_URL=https://tu-tienda.myshopify.com
SHOPIFY_ACCESS_TOKEN=shpat_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
SHOPIFY_API_VERSION=2025-10
HOST=0.0.0.0
PORT=8000
LOG_LEVEL=INFO
```

#### Obtener el Access Token de Shopify

1. Ve a tu panel de administración de Shopify
2. Navega a **Settings > Apps and sales channels > Develop apps**
3. Crea una nueva app o selecciona una existente
4. En **Configuration**, configura los siguientes permisos:
   - `read_inventory`
   - `write_inventory`
   - `read_products`
5. Instala la app y copia el **Admin API access token**

## Uso

### Iniciar el servidor

```bash
python -m odoo_shopify_connector.main
```

O con uvicorn directamente:

```bash
uvicorn odoo_shopify_connector.api:app --host 0.0.0.0 --port 8000
```

El servidor estará disponible en `http://localhost:8000`

### Verificar que está funcionando

```bash
curl http://localhost:8000/health
```

Respuesta esperada:
```json
{
  "status": "healthy"
}
```

### Documentación de la API

FastAPI genera documentación automática. Accede a:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## Configuración de Odoo

Para que Odoo envíe webhooks cuando el stock cambia, necesitas configurar una **Acción Automatizada**.

### Crear Acción Automatizada en Odoo

1. Ve a **Ajustes > Técnico > Automatización > Acciones Automatizadas**
2. Crea una nueva acción con los siguientes parámetros:

**Configuración básica:**
- **Nombre**: Sincronizar Stock con Shopify
- **Modelo**: Stock Quant (`stock.quant`)
- **Disparador**: On Update (Al Actualizar)
- **Filtro de Dominio**: `[('product_id.default_code', '!=', False)]` (solo productos con SKU)

**Acción a ejecutar:**
- **Tipo de Acción**: Execute Python Code

**Código Python:**

```python
import requests
import json

# URL del conector (ajusta según tu configuración)
CONNECTOR_URL = "http://tu-servidor:8000/webhook/odoo/stock"

for record in records:
    # Solo procesar si el producto tiene SKU (default_code en Odoo)
    if record.product_id.default_code:
        payload = {
            "product_reference_code": record.product_id.default_code,
            "available_quantity": int(record.quantity),
            "location_id": record.location_id.id
        }

        try:
            response = requests.post(
                CONNECTOR_URL,
                json=payload,
                timeout=10
            )

            if response.status_code != 200:
                raise UserError(f"Error al sincronizar con Shopify: {response.text}")

        except Exception as e:
            # Log del error (no bloquear la operación en Odoo)
            import logging
            _logger = logging.getLogger(__name__)
            _logger.error(f"Error al enviar webhook a Shopify: {str(e)}")
```

### Formato del Webhook

El webhook de Odoo debe enviar un JSON con el siguiente formato:

```json
{
  "product_reference_code": "PROD-SKU-001",
  "available_quantity": 25,
  "location_id": 8
}
```

**Campos:**
- `product_reference_code` (requerido): SKU del producto (debe coincidir exactamente con el SKU en Shopify)
- `available_quantity` (requerido): Cantidad total disponible (≥ 0)
- `location_id` (opcional): ID de ubicación en Odoo (solo para logging)

## Arquitectura Técnica

### Componentes

1. **`models.py`**: Modelos Pydantic para validación de datos
2. **`config.py`**: Gestión de configuración y variables de entorno
3. **`shopify_service.py`**: Servicio que encapsula la lógica de Shopify GraphQL
4. **`api.py`**: API FastAPI con el endpoint del webhook
5. **`main.py`**: Punto de entrada de la aplicación

### Modelo de Consistencia

Este conector implementa un modelo de **consistencia eventual**:

- **Sin colas**: Los webhooks se procesan sincrónicamente
- **Sin reintentos**: Si falla una actualización, se espera al siguiente cambio de stock
- **Sin transacciones**: No hay garantías ACID entre Odoo y Shopify

### Riesgos Aceptados

⚠️ **Importante**: Este diseño prioriza simplicidad sobre robustez:

1. **Webhook Prematuro**: El webhook podría dispararse antes del commit de la transacción en Odoo
2. **Webhook Perdido**: Si Shopify está caído, la actualización se pierde
3. **Dependencia de SKU**: El SKU debe estar perfectamente sincronizado entre sistemas

## Respuestas de la API

### Éxito (200 OK)

```json
{
  "success": true,
  "message": "Stock sincronizado exitosamente para SKU 'PROD-001'",
  "sku": "PROD-001",
  "quantity_updated": 25,
  "delta": 5
}
```

### Error - Producto no encontrado (500)

```json
{
  "success": false,
  "message": "Producto con SKU 'PROD-999' no encontrado en Shopify"
}
```

### Error - Payload inválido (400)

```json
{
  "detail": [
    {
      "loc": ["body", "product_reference_code"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

### Error - Shopify GraphQL (500)

```json
{
  "success": false,
  "message": "Error al comunicar con Shopify: GraphQL errors: ..."
}
```

## Testing

### Test manual con curl

```bash
curl -X POST http://localhost:8000/webhook/odoo/stock \
  -H "Content-Type: application/json" \
  -d '{
    "product_reference_code": "TU-SKU-AQUI",
    "available_quantity": 10
  }'
```

### Script de test de Python existente

El repositorio incluye un script de test en `tests/odoo_shopify_stock.py` para probar la comunicación con Shopify directamente.

## Despliegue en Producción

### Consideraciones

1. **HTTPS**: El conector debe estar detrás de un proxy inverso (nginx, Traefik) con HTTPS
2. **Firewall**: Asegúrate de que Odoo pueda alcanzar el conector
3. **Logging**: Configura rotación de logs
4. **Monitoring**: Implementa health checks y alertas
5. **Seguridad**: Considera agregar autenticación al webhook

### Ejemplo con Docker

```dockerfile
FROM python:3.13-slim

WORKDIR /app
COPY . /app

RUN pip install -e .

CMD ["python", "-m", "odoo_shopify_connector.main"]
```

```bash
docker build -t odoo-shopify-connector .
docker run -d \
  -p 8000:8000 \
  --env-file .env \
  --name connector \
  odoo-shopify-connector
```

### Ejemplo con systemd

Crea `/etc/systemd/system/odoo-shopify-connector.service`:

```ini
[Unit]
Description=Odoo-Shopify Stock Connector
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/odoo-shopify-connector
Environment="PATH=/opt/odoo-shopify-connector/venv/bin"
EnvironmentFile=/opt/odoo-shopify-connector/.env
ExecStart=/opt/odoo-shopify-connector/venv/bin/python -m odoo_shopify_connector.main
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable odoo-shopify-connector
sudo systemctl start odoo-shopify-connector
```

## Troubleshooting

### El webhook no llega al conector

1. Verifica que el conector esté corriendo: `curl http://localhost:8000/health`
2. Revisa los logs de Odoo para ver si hay errores al enviar el webhook
3. Verifica que la URL en la Acción Automatizada sea correcta
4. Asegúrate de que no haya firewall bloqueando la conexión

### "Producto no encontrado en Shopify"

1. Verifica que el SKU en Odoo coincida EXACTAMENTE con el SKU en Shopify
2. Revisa en Shopify Admin que el producto tenga SKU configurado
3. Prueba buscar el producto manualmente en Shopify con el SKU

### "Error al comunicar con Shopify"

1. Verifica que `SHOPIFY_STORE_URL` y `SHOPIFY_ACCESS_TOKEN` sean correctos
2. Verifica que el token tenga los permisos necesarios
3. Revisa los logs del conector para más detalles

## Logs

Los logs incluyen información detallada sobre cada sincronización:

```
2025-01-13 10:30:45 - odoo_shopify_connector.api - INFO - Webhook recibido de Odoo - SKU: PROD-001, Cantidad: 25
2025-01-13 10:30:45 - odoo_shopify_connector.shopify_service - INFO - Iniciando sincronización de stock para SKU: PROD-001, cantidad: 25
2025-01-13 10:30:45 - odoo_shopify_connector.shopify_service - INFO - Ubicación obtenida: Mi Tienda (ID: gid://shopify/Location/123)
2025-01-13 10:30:46 - odoo_shopify_connector.shopify_service - INFO - Variante encontrada - ID: gid://shopify/ProductVariant/456
2025-01-13 10:30:46 - odoo_shopify_connector.shopify_service - INFO - Stock actual en Shopify para SKU PROD-001: 20
2025-01-13 10:30:46 - odoo_shopify_connector.shopify_service - INFO - Ajustando inventario: 20 -> 25 (delta: 5)
2025-01-13 10:30:46 - odoo_shopify_connector.shopify_service - INFO - Inventario ajustado exitosamente
```

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
