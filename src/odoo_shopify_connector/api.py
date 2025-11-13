"""
API FastAPI para el conector Odoo-Shopify.

Provee un endpoint para recibir webhooks de Odoo y sincronizar stock con Shopify.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse

from .models import OdooWebhookPayload, WebhookResponse
from .shopify_service import ShopifyService, ShopifyGraphQLError
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
    logger.info(f"Shopify Store: {settings.SHOPIFY_STORE_URL}")
    logger.info(f"API Version: {settings.SHOPIFY_API_VERSION}")
    yield
    logger.info("Apagando conector Odoo-Shopify...")


# Crear aplicación FastAPI
app = FastAPI(
    title="Conector Odoo-Shopify Stock",
    description="API para sincronizar inventario de Odoo a Shopify",
    version="1.0.0",
    lifespan=lifespan
)

# Instancia del servicio de Shopify (singleton)
shopify_service = ShopifyService()


@app.get("/")
async def root():
    """
    Endpoint raíz para verificar que la API está funcionando.
    """
    return {
        "service": "Odoo-Shopify Stock Connector",
        "status": "running",
        "version": "1.0.0"
    }


@app.get("/health")
async def health_check():
    """
    Health check endpoint.
    """
    return {"status": "healthy"}


@app.post(
    "/webhook/odoo/stock",
    response_model=WebhookResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {
            "description": "Stock sincronizado exitosamente",
            "model": WebhookResponse
        },
        400: {
            "description": "Payload inválido"
        },
        500: {
            "description": "Error al sincronizar con Shopify"
        }
    }
)
async def odoo_stock_webhook(payload: OdooWebhookPayload) -> WebhookResponse:
    """
    Endpoint para recibir webhooks de Odoo cuando el stock cambia.

    Este endpoint:
    1. Valida el payload del webhook usando Pydantic
    2. Busca el producto en Shopify por SKU
    3. Calcula el delta de inventario
    4. Ajusta el stock en Shopify

    Args:
        payload: Datos del webhook de Odoo (validado por Pydantic)

    Returns:
        WebhookResponse: Resultado de la sincronización

    Raises:
        HTTPException 400: Si el payload es inválido
        HTTPException 500: Si hay errores al sincronizar con Shopify
    """
    logger.info(
        f"Webhook recibido de Odoo - SKU: {payload.sku}, "
        f"Cantidad: {payload.quantity}"
    )

    try:
        # Sincronizar stock con Shopify
        result = shopify_service.sync_stock(
            sku=payload.sku,
            new_quantity=payload.quantity
        )

        # Si la sincronización falló, devolver error 500
        if not result["success"]:
            logger.error(f"Error al sincronizar: {result['message']}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result["message"]
            )

        # Sincronización exitosa
        logger.info(f"Stock sincronizado exitosamente: {result}")
        return WebhookResponse(
            success=True,
            message=result["message"],
            sku=result.get("sku"),
            quantity_updated=result.get("quantity_updated"),
            delta=result.get("delta")
        )

    except ShopifyGraphQLError as e:
        # Error específico de Shopify GraphQL
        logger.error(f"Error de Shopify GraphQL: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al comunicar con Shopify: {str(e)}"
        )

    except Exception as e:
        # Error inesperado
        logger.exception(f"Error inesperado al procesar webhook: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error interno del servidor: {str(e)}"
        )


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """
    Handler personalizado para HTTPException.
    Asegura que Odoo reciba respuestas consistentes.
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "message": exc.detail
        }
    )
