"""
Conector Odoo-Shopify Stock Synchronization.

Un conector unidireccional (Odoo -> Shopify) para sincronización de inventario
mediante consulta directa a la API de Odoo.
"""
from .api import app
from .config import settings
from .shopify_service import ShopifyService
from .odoo_client import OdooClient
from .sync_service import SyncService
from .models import OdooStockQuant, SyncResult, SyncSummary

__version__ = "2.0.0"
__all__ = [
    "app",
    "settings",
    "ShopifyService",
    "OdooClient",
    "SyncService",
    "OdooStockQuant",
    "SyncResult",
    "SyncSummary",
]
