"""
API FastAPI para el conector Odoo-Shopify.

Provee endpoints para sincronizar inventario de Odoo a Shopify.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status, BackgroundTasks
from fastapi.responses import JSONResponse

from .models import SyncSummary
from .sync_service import SyncService
from .odoo_client import OdooConnectionError
from .config import settings

# Configurar logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifecycle manager para FastAPI.
    Inicializa y limpia recursos.
    """
    logger.info("Iniciando conector Odoo-Shopify...")
    logger.info(f"Odoo: {settings.ODOO_URL} - DB: {settings.ODOO_DATABASE}")
    logger.info(f"Shopify Store: {settings.SHOPIFY_STORE_URL}")
    logger.info(f"Ubicación de Odoo a sincronizar: {settings.ODOO_LOCATION_ID}")
    yield
    logger.info("Apagando conector Odoo-Shopify...")


# Crear aplicación FastAPI
app = FastAPI(
    title="Conector Odoo-Shopify Stock",
    description="API para sincronizar inventario de Odoo a Shopify con detección de cambios (optimizado)",
    version="2.1.0",
    lifespan=lifespan
)

# Instancia del servicio de sincronización (singleton)
sync_service = SyncService()


@app.get("/")
async def root():
    """
    Endpoint raíz para verificar que la API está funcionando.
    """
    return {
        "service": "Odoo-Shopify Stock Connector",
        "status": "running",
        "version": "2.1.0",
        "mode": "pull_optimized",
        "description": "Sincroniza inventario con detección de cambios (95% menos API calls)"
    }


@app.get("/health")
async def health_check():
    """
    Health check endpoint.
    """
    return {"status": "healthy"}


@app.get("/test-connections")
async def test_connections():
    """
    Prueba las conexiones con Odoo y Shopify.

    Returns:
        Estado de las conexiones
    """
    logger.info("Probando conexiones...")
    try:
        result = sync_service.test_connections()
        return result
    except Exception as e:
        logger.exception(f"Error al probar conexiones: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al probar conexiones: {str(e)}"
        )


@app.post(
    "/sync",
    response_model=SyncSummary,
    status_code=status.HTTP_200_OK,
    responses={
        200: {
            "description": "Sincronización completada (puede haber productos fallidos)",
            "model": SyncSummary
        },
        500: {
            "description": "Error al conectar con Odoo"
        }
    }
)
async def sync_inventory() -> SyncSummary:
    """
    Sincroniza inventario usando BULK con detección de cambios (OPTIMIZADO).

    Este endpoint usa el modo bulk OPTIMIZADO para máxima eficiencia:
    1. Lee inventario de Odoo
    2. Detecta cambios vs última sincronización
    3. Si NO hay cambios → retorna sin llamadas a Shopify (95% ahorro)
    4. Solo sincroniza productos nuevos/modificados/eliminados
    5. Actualiza snapshot automáticamente

    Returns:
        SyncSummary: Resumen con estadísticas de cambios y ahorro de API

    Raises:
        HTTPException 500: Si hay error al conectar con Odoo
    """
    logger.info("Iniciando sincronización OPTIMIZADA de inventario...")

    try:
        summary = sync_service.sync_all_inventory_bulk_with_changes()
        logger.info(
            f"Sincronización OPTIMIZADA completada: {summary.successful}/{summary.total_products} exitosos, "
            f"{summary.unchanged} sin cambios, {summary.new} nuevos, {summary.modified} modificados, "
            f"{summary.total_time_seconds:.2f}s"
        )
        return summary

    except OdooConnectionError as e:
        logger.error(f"Error de conexión con Odoo: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al conectar con Odoo: {str(e)}"
        )

    except Exception as e:
        logger.exception(f"Error inesperado durante sincronización: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error interno del servidor: {str(e)}"
        )


@app.post("/sync/single", response_model=SyncSummary)
async def sync_inventory_single() -> SyncSummary:
    """
    Sincroniza inventario producto por producto (modo tradicional).

    Este modo es más lento pero puede ser útil para debugging.
    Se recomienda usar el endpoint /sync (bulk) para producción.

    Returns:
        SyncSummary: Resumen de la sincronización

    Raises:
        HTTPException 500: Si hay error al conectar con Odoo
    """
    logger.info("Iniciando sincronización SINGLE de inventario...")

    try:
        summary = sync_service.sync_all_inventory()
        logger.info(f"Sincronización SINGLE completada: {summary.successful}/{summary.total_products} exitosos")
        return summary

    except OdooConnectionError as e:
        logger.error(f"Error de conexión con Odoo: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al conectar con Odoo: {str(e)}"
        )

    except Exception as e:
        logger.exception(f"Error inesperado durante sincronización: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error interno del servidor: {str(e)}"
        )


@app.post("/sync/async")
async def sync_inventory_async(background_tasks: BackgroundTasks):
    """
    Inicia la sincronización de inventario BULK en segundo plano.

    Este endpoint retorna inmediatamente y ejecuta la sincronización
    en background. Útil para evitar timeouts en sincronizaciones muy largas.

    Returns:
        Mensaje de confirmación
    """
    logger.info("Iniciando sincronización BULK en background...")

    def run_sync():
        try:
            summary = sync_service.sync_all_inventory_bulk()
            logger.info(
                f"Sincronización BULK background completada: {summary.successful}/{summary.total_products} exitosos, "
                f"{summary.total_batches} batches, {summary.total_time_seconds:.2f}s"
            )
        except Exception as e:
            logger.exception(f"Error en sincronización background: {e}")

    background_tasks.add_task(run_sync)

    return {
        "message": "Sincronización BULK iniciada en segundo plano",
        "status": "processing",
        "mode": "bulk"
    }


@app.get("/snapshot/info")
async def get_snapshot_info():
    """
    Obtiene información del snapshot actual.

    Returns:
        - exists: Si existe el snapshot
        - last_sync: Fecha de última sincronización
        - total_products: Número de productos en snapshot
        - file_size_kb: Tamaño del archivo
    """
    try:
        info = sync_service.snapshot_service.get_snapshot_info()
        return info
    except Exception as e:
        logger.exception(f"Error al obtener info de snapshot: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener info: {str(e)}"
        )


@app.post("/snapshot/reset")
async def reset_snapshot():
    """
    Resetea el snapshot para forzar sincronización completa.

    Útil para:
    - Después de migración
    - Corrupción de datos
    - Testing

    Returns:
        Confirmación de reset
    """
    try:
        success = sync_service.snapshot_service.reset_snapshot()
        if success:
            return {
                "success": True,
                "message": "Snapshot eliminado. Próxima sync será completa."
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error al eliminar snapshot"
            )
    except Exception as e:
        logger.exception(f"Error al resetear snapshot: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error: {str(e)}"
        )


@app.get("/sync/preview")
async def preview_changes():
    """
    Preview de cambios sin ejecutar sincronización.

    Muestra qué productos se sincronizarían sin realmente ejecutar
    la sincronización con Shopify.

    Returns:
        - changes: Número de productos nuevos/modificados/eliminados
        - products_to_sync: Lista de SKUs que se sincronizarían
        - estimated_time: Tiempo estimado de sincronización
        - estimated_api_calls: Número estimado de llamadas API
    """
    try:
        # Leer inventario de Odoo
        stock_quants = sync_service.odoo_client.get_inventory_by_location(settings.ODOO_LOCATION_ID)

        if not stock_quants:
            return {
                "changes": 0,
                "products_to_sync": [],
                "estimated_time_seconds": 0,
                "estimated_api_calls": 0
            }

        # Cargar snapshot y detectar cambios
        snapshot = sync_service.snapshot_service.load_snapshot()
        changes = sync_service.snapshot_service.compare_with_current(stock_quants, snapshot)

        # Calcular estimaciones
        products_to_sync = changes.new_products + changes.modified_products
        skus_to_sync = [p.sku for p in products_to_sync] + changes.deleted_skus

        # Estimar tiempo (aprox 0.2s por producto + 1s por batch)
        estimated_batches = (len(products_to_sync) // 250) + 1 if products_to_sync else 0
        estimated_time = (len(products_to_sync) * 0.2) + (estimated_batches * 1)

        # Estimar API calls
        estimated_api_calls = len(products_to_sync) + estimated_batches

        return {
            "total_products_in_odoo": len(stock_quants),
            "changes_detected": {
                "new": len(changes.new_products),
                "modified": len(changes.modified_products),
                "deleted": len(changes.deleted_skus),
                "unchanged": changes.unchanged_products,
                "total": changes.total_changes
            },
            "products_to_sync": skus_to_sync,
            "estimated_time_seconds": round(estimated_time, 1),
            "estimated_api_calls": estimated_api_calls,
            "estimated_batches": estimated_batches
        }

    except OdooConnectionError as e:
        logger.error(f"Error de conexión con Odoo: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al conectar con Odoo: {str(e)}"
        )
    except Exception as e:
        logger.exception(f"Error en preview: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error: {str(e)}"
        )


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """
    Handler personalizado para HTTPException.
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "message": exc.detail
        }
    )
