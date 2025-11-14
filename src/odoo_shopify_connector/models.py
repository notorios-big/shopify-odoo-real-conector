"""
Modelos Pydantic para validación de datos del conector Odoo-Shopify.
"""
from datetime import datetime
from pydantic import BaseModel, Field


class OdooStockQuant(BaseModel):
    """
    Modelo para representar un registro de stock.quant de Odoo.
    """
    product_id: int = Field(description="ID del producto en Odoo")
    product_name: str = Field(description="Nombre del producto")
    sku: str = Field(description="SKU del producto (default_code)")
    quantity: float = Field(description="Cantidad disponible", ge=0)
    location_id: int = Field(description="ID de ubicación en Odoo")

    class Config:
        """Configuración del modelo"""
        json_schema_extra = {
            "example": {
                "product_id": 123,
                "product_name": "Manteca de Karité",
                "sku": "MANT-KAR-500",
                "quantity": 25.0,
                "location_id": 28
            }
        }


class ShopifyInventoryUpdate(BaseModel):
    """
    Modelo interno para representar una actualización de inventario en Shopify.
    """
    inventory_item_id: str = Field(description="ID del inventory item en Shopify")
    location_id: str = Field(description="ID de la ubicación en Shopify")
    current_quantity: int = Field(description="Cantidad actual en Shopify")
    new_quantity: int = Field(description="Cantidad nueva deseada")
    delta: int = Field(description="Diferencia a ajustar")

    @property
    def needs_adjustment(self) -> bool:
        """Determina si se necesita hacer un ajuste"""
        return self.delta != 0


class SyncResult(BaseModel):
    """
    Modelo para el resultado de una sincronización.
    """
    success: bool = Field(description="Indica si la operación fue exitosa")
    message: str = Field(description="Mensaje descriptivo del resultado")
    sku: str | None = Field(default=None, description="SKU procesado")
    quantity_updated: int | None = Field(default=None, description="Cantidad actualizada")
    delta: int | None = Field(default=None, description="Ajuste aplicado")


class BulkInventoryAdjustment(BaseModel):
    """
    Modelo para representar un ajuste de inventario en bulk.
    """
    inventory_item_id: str = Field(description="ID del inventory item en Shopify")
    available_delta: int = Field(description="Delta a ajustar")
    sku: str | None = Field(default=None, description="SKU del producto (para tracking)")

    class Config:
        """Configuración del modelo"""
        json_schema_extra = {
            "example": {
                "inventory_item_id": "gid://shopify/InventoryItem/12345",
                "available_delta": 5,
                "sku": "PROD-001"
            }
        }


class BulkUpdateResult(BaseModel):
    """
    Modelo para el resultado de una actualización bulk.
    """
    success: bool = Field(description="Indica si la operación fue exitosa")
    items_updated: int = Field(description="Número de items actualizados")
    items_failed: int = Field(description="Número de items que fallaron")
    user_errors: list[dict] = Field(default_factory=list, description="Errores reportados por Shopify")
    throttle_status: dict | None = Field(default=None, description="Estado del throttle/rate limit")


class SyncSummary(BaseModel):
    """
    Modelo para el resumen de una sincronización completa.
    """
    total_products: int = Field(description="Total de productos procesados")
    successful: int = Field(description="Productos sincronizados exitosamente")
    failed: int = Field(description="Productos que fallaron")
    skipped: int = Field(description="Productos omitidos (sin SKU)")
    unchanged: int = Field(default=0, description="Productos sin cambios (no sincronizados)")
    new: int = Field(default=0, description="Productos nuevos detectados")
    modified: int = Field(default=0, description="Productos modificados detectados")
    deleted: int = Field(default=0, description="Productos eliminados de Odoo")
    results: list[SyncResult] = Field(default_factory=list, description="Resultados individuales")
    bulk_mode: bool = Field(default=False, description="Indica si se usó modo bulk")
    total_batches: int = Field(default=0, description="Número total de batches procesados")
    total_time_seconds: float = Field(default=0.0, description="Tiempo total de sincronización")
    snapshot_updated: bool = Field(default=False, description="Indica si se actualizó el snapshot")


class SnapshotProduct(BaseModel):
    """Datos de un producto en el snapshot"""
    sku: str = Field(description="SKU del producto")
    quantity: int = Field(description="Cantidad disponible en Odoo")
    product_name: str = Field(description="Nombre del producto")
    product_id: int = Field(description="ID del producto en Odoo")
    last_updated: datetime = Field(description="Última actualización")


class SyncSnapshot(BaseModel):
    """Snapshot del estado del inventario en la última sincronización"""
    last_sync_timestamp: datetime = Field(description="Timestamp de la última sincronización")
    total_products: int = Field(description="Total de productos en el snapshot")
    products: dict[str, SnapshotProduct] = Field(default_factory=dict, description="Productos por SKU")


class ChangeDetectionResult(BaseModel):
    """Resultado de la detección de cambios"""
    new_products: list[OdooStockQuant] = Field(default_factory=list, description="Productos nuevos")
    modified_products: list[OdooStockQuant] = Field(default_factory=list, description="Productos modificados")
    deleted_skus: list[str] = Field(default_factory=list, description="SKUs eliminados de Odoo")
    unchanged_products: int = Field(default=0, description="Productos sin cambios")
    total_changes: int = Field(default=0, description="Total de cambios detectados")
