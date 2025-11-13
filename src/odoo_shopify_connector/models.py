"""
Modelos Pydantic para validación de datos del conector Odoo-Shopify.
"""
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


class SyncSummary(BaseModel):
    """
    Modelo para el resumen de una sincronización completa.
    """
    total_products: int = Field(description="Total de productos procesados")
    successful: int = Field(description="Productos sincronizados exitosamente")
    failed: int = Field(description="Productos que fallaron")
    skipped: int = Field(description="Productos omitidos (sin SKU)")
    results: list[SyncResult] = Field(default_factory=list, description="Resultados individuales")
