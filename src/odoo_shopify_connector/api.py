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
    description="API para sincronizar inventario de Odoo a Shopify mediante consulta directa",
    version="2.0.0",
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
        "version": "2.0.0",
        "mode": "pull",
        "description": "Consulta inventario de Odoo y sincroniza con Shopify"
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
    Sincroniza todo el inventario usando actualización masiva (BULK - RECOMENDADO).

    Este endpoint usa el modo bulk para máxima eficiencia:
    1. Lee todo el inventario de la ubicación configurada en Odoo
    2. Agrupa productos en batches de hasta 250 items
    3. Actualiza cada batch con una sola llamada GraphQL
    4. Incluye retry automático y monitoreo de rate limits

    Returns:
        SyncSummary: Resumen de la sincronización con estadísticas de batches

    Raises:
        HTTPException 500: Si hay error al conectar con Odoo
    """
    logger.info("Iniciando sincronización BULK de inventario...")

    try:
        summary = sync_service.sync_all_inventory_bulk()
        logger.info(
            f"Sincronización BULK completada: {summary.successful}/{summary.total_products} exitosos, "
            f"{summary.total_batches} batches, {summary.total_time_seconds:.2f}s"
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
