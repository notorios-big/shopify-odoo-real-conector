"""
Conector Odoo-Shopify Stock Synchronization.

Un conector unidireccional (Odoo -> Shopify) para sincronización de inventario.
"""
from .api import app
from .config import settings
from .shopify_service import ShopifyService
from .models import OdooWebhookPayload, WebhookResponse

__version__ = "1.0.0"
__all__ = [
    "app",
    "settings",
    "ShopifyService",
    "OdooWebhookPayload",
    "WebhookResponse",
]
