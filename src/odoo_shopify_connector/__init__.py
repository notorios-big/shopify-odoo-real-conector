"""
Conector Odoo-Shopify Stock Synchronization.

Un conector unidireccional (Odoo -> Shopify) para sincronización de inventario
con detección de cambios optimizada (v2.1.0).
"""
from .api import app
from .config import settings
from .shopify_service import ShopifyService
from .odoo_client import OdooClient
from .sync_service import SyncService
from .snapshot_service import SnapshotService
from .models import (
    OdooStockQuant,
    SyncResult,
    SyncSummary,
    SyncSnapshot,
    SnapshotProduct,
    ChangeDetectionResult,
)

__version__ = "2.1.0"
__all__ = [
    "app",
    "settings",
    "ShopifyService",
    "OdooClient",
    "SyncService",
    "SnapshotService",
    "OdooStockQuant",
    "SyncResult",
    "SyncSummary",
    "SyncSnapshot",
    "SnapshotProduct",
    "ChangeDetectionResult",
]
