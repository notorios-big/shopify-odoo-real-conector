"""
Punto de entrada principal para el conector Odoo-Shopify.
"""
import uvicorn

from .config import settings


def main():
    """
    Ejecuta el servidor FastAPI con uvicorn.
    """
    uvicorn.run(
        "odoo_shopify_connector.api:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=False,  # Desactivar reload en producción
        log_level=settings.LOG_LEVEL.lower()
    )


if __name__ == "__main__":
    main()
