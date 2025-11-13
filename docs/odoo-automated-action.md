# Configuración de Acción Automatizada en Odoo

Este documento proporciona instrucciones paso a paso para configurar Odoo para enviar webhooks al conector cuando el stock cambia.

## Requisitos Previos

- Acceso de administrador a Odoo
- Modo desarrollador activado en Odoo
- El conector FastAPI debe estar corriendo y accesible desde Odoo

## Paso 1: Activar Modo Desarrollador

Si no está activado:

1. Ve a **Ajustes**
2. Scroll hasta el final
3. Click en **Activar el modo de desarrollador**

## Paso 2: Crear Acción Automatizada

### 2.1 Navegar a Acciones Automatizadas

1. Ve a **Ajustes > Técnico > Automatización > Acciones Automatizadas**
2. Click en **Crear** (o **Nuevo**)

### 2.2 Configuración Básica

Completa los siguientes campos:

| Campo | Valor |
|-------|-------|
| **Nombre de la acción** | `Sincronizar Stock con Shopify` |
| **Modelo** | `Stock Quant` (stock.quant) |
| **Disparador** | `On Update` (Al Actualizar) |
| **Aplicar en** | Dejar vacío o filtrar por ubicaciones específicas |

### 2.3 Filtro de Dominio (Opcional pero Recomendado)

Para evitar procesar productos sin SKU, agrega el siguiente filtro:

```python
[('product_id.default_code', '!=', False)]
```

Esto asegura que solo se procesen productos que tengan un SKU configurado.

### 2.4 Configurar Acción Python

En la sección **Acción**:

1. Selecciona **Tipo de Acción**: `Execute Python Code`
2. En el campo **Código Python**, pega el siguiente código:

```python
import requests
import json
import logging

_logger = logging.getLogger(__name__)

# ============================================
# CONFIGURACIÓN - Ajusta estos valores
# ============================================
CONNECTOR_URL = "http://localhost:8000/webhook/odoo/stock"  # URL del conector FastAPI
TIMEOUT_SECONDS = 10  # Timeout para la petición HTTP
BLOCK_ON_ERROR = False  # Si True, bloquea la operación en Odoo si falla la sincronización

# ============================================
# LÓGICA DE SINCRONIZACIÓN
# ============================================

for record in records:
    # Solo procesar si el producto tiene SKU (default_code)
    if not record.product_id.default_code:
        _logger.warning(
            f"Producto {record.product_id.name} (ID: {record.product_id.id}) "
            "no tiene SKU configurado. No se sincronizará con Shopify."
        )
        continue

    # Preparar payload para el webhook
    payload = {
        "product_reference_code": record.product_id.default_code,
        "available_quantity": int(record.quantity),
        "location_id": record.location_id.id
    }

    _logger.info(
        f"Sincronizando stock con Shopify - SKU: {payload['product_reference_code']}, "
        f"Cantidad: {payload['available_quantity']}, Ubicación: {record.location_id.name}"
    )

    try:
        # Enviar webhook al conector
        response = requests.post(
            CONNECTOR_URL,
            json=payload,
            timeout=TIMEOUT_SECONDS,
            headers={'Content-Type': 'application/json'}
        )

        # Verificar respuesta
        if response.status_code == 200:
            response_data = response.json()
            _logger.info(
                f"✓ Stock sincronizado exitosamente: {response_data.get('message', 'OK')}"
            )
        else:
            error_msg = f"Error HTTP {response.status_code}: {response.text}"
            _logger.error(f"✗ Error al sincronizar stock: {error_msg}")

            if BLOCK_ON_ERROR:
                raise UserError(
                    f"No se pudo sincronizar el stock con Shopify: {error_msg}"
                )

    except requests.exceptions.Timeout:
        error_msg = f"Timeout al intentar conectar con el conector (>{TIMEOUT_SECONDS}s)"
        _logger.error(f"✗ {error_msg}")

        if BLOCK_ON_ERROR:
            raise UserError(error_msg)

    except requests.exceptions.ConnectionError as e:
        error_msg = f"Error de conexión con el conector: {str(e)}"
        _logger.error(f"✗ {error_msg}")

        if BLOCK_ON_ERROR:
            raise UserError(error_msg)

    except Exception as e:
        error_msg = f"Error inesperado al sincronizar stock: {str(e)}"
        _logger.exception(f"✗ {error_msg}")

        if BLOCK_ON_ERROR:
            raise UserError(error_msg)
```

## Paso 3: Guardar y Probar

### 3.1 Guardar la Acción

Click en **Guardar**

### 3.2 Probar la Acción

Para probar que funciona:

1. Ve a **Inventario > Productos**
2. Selecciona un producto que tenga SKU configurado
3. Modifica su stock (ej. hacer un ajuste de inventario)
4. Verifica en los logs del conector que se recibió el webhook:

```bash
# En el servidor donde corre el conector
tail -f /ruta/a/logs/conector.log
```

O si el conector está corriendo en consola, deberías ver:

```
2025-01-13 10:30:45 - odoo_shopify_connector.api - INFO - Webhook recibido de Odoo - SKU: TU-SKU, Cantidad: 10
```

### 3.3 Verificar en Shopify

1. Ve a tu panel de administración de Shopify
2. Navega al producto con el mismo SKU
3. Verifica que el inventario se haya actualizado

## Configuración Avanzada

### Filtrar por Ubicaciones Específicas

Si solo quieres sincronizar stock de ubicaciones específicas, agrega un filtro de dominio:

```python
[
    ('product_id.default_code', '!=', False),
    ('location_id.name', '=', 'Stock Principal')  # Solo ubicación "Stock Principal"
]
```

O para múltiples ubicaciones:

```python
[
    ('product_id.default_code', '!=', False),
    ('location_id.name', 'in', ['Stock Principal', 'Almacén A', 'Almacén B'])
]
```

### Modo de Bloqueo (BLOCK_ON_ERROR)

En el código Python, ajusta la variable `BLOCK_ON_ERROR`:

- **`False` (Recomendado)**: Los errores de sincronización se registran en el log pero NO bloquean la operación en Odoo
- **`True` (Modo estricto)**: Si falla la sincronización, la operación en Odoo se bloquea y se muestra un error al usuario

### Autenticación del Webhook (Opcional)

Si configuraste autenticación en el conector, modifica la petición:

```python
# Ejemplo con Bearer token
headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer TU_TOKEN_SECRETO'
}

response = requests.post(
    CONNECTOR_URL,
    json=payload,
    timeout=TIMEOUT_SECONDS,
    headers=headers
)
```

## Troubleshooting

### La acción no se dispara

**Causa**: El disparador puede no estar configurado correctamente

**Solución**:
1. Verifica que el disparador sea `On Update`
2. Prueba cambiar a `On Create or Update` si es necesario
3. Verifica que el filtro de dominio no esté excluyendo todos los registros

### Error: "Module 'requests' not found"

**Causa**: La biblioteca `requests` no está instalada en el entorno de Odoo

**Solución**:
```bash
# En el servidor de Odoo
pip install requests
# O
pip3 install requests

# Luego reinicia Odoo
sudo systemctl restart odoo
```

### Los logs muestran "no tiene SKU configurado"

**Causa**: El producto no tiene el campo `default_code` (SKU) configurado

**Solución**:
1. Ve al producto en Odoo
2. En la pestaña **Información general**
3. Completa el campo **Referencia interna** (este es el SKU)
4. Asegúrate de que coincida EXACTAMENTE con el SKU en Shopify

### Error: "Connection refused"

**Causa**: El conector no está corriendo o la URL es incorrecta

**Solución**:
1. Verifica que el conector esté corriendo: `curl http://localhost:8000/health`
2. Verifica la URL en `CONNECTOR_URL`
3. Si Odoo y el conector están en servidores diferentes, usa la IP/dominio correcto
4. Verifica firewall y puertos abiertos

### El stock se sincroniza pero con retraso

**Causa**: Normal con el modelo de consistencia eventual

**Explicación**: El conector procesa webhooks sincrónicamente. Pequeños retrasos son normales, especialmente si hay múltiples actualizaciones rápidas.

### Errores de "Race Condition" o valores incorrectos

**Causa**: Webhook disparado antes del commit de la transacción en Odoo

**Mitigación**:
- Este es un riesgo aceptado del diseño simple
- La próxima actualización corregirá el valor
- Para mayor robustez, considera implementar colas (queue_job)

## Monitoreo

### Ver logs de la Acción Automatizada

Los logs del código Python aparecen en:

1. **Logs de Odoo**: `/var/log/odoo/odoo-server.log` (ubicación puede variar)
2. **En el navegador**: Si ejecutas Odoo en modo debug, pueden aparecer en la consola

### Ver logs del Conector

Consulta los logs del conector FastAPI para ver las peticiones recibidas:

```bash
# Si usas systemd
sudo journalctl -u odoo-shopify-connector -f

# Si corre en consola, los logs aparecen directamente
```

## Mejoras Futuras

Posibles mejoras a considerar:

1. **Colas de trabajo**: Usar `queue_job` para desacoplar el webhook del trigger
2. **Reintentos**: Implementar lógica de reintentos con backoff exponencial
3. **Batch processing**: Agrupar múltiples cambios antes de sincronizar
4. **Autenticación**: Agregar token de autenticación entre Odoo y el conector
5. **Rate limiting**: Controlar la frecuencia de webhooks

## Referencias

- [Documentación de Acciones Automatizadas en Odoo](https://www.odoo.com/documentation/16.0/developer/reference/backend/actions.html#automated-actions-ir-cron)
- [API de Python en Odoo](https://www.odoo.com/documentation/16.0/developer/reference/backend/orm.html)
- [Documentación del Conector](../README.md)
