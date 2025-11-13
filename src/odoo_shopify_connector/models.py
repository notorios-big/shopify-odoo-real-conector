"""
Modelos Pydantic para validación de datos del conector Odoo-Shopify.
"""
from pydantic import BaseModel, Field, field_validator


class OdooWebhookPayload(BaseModel):
    """
    Modelo para validar el payload del webhook de Odoo.

    Este modelo valida que el webhook contenga el SKU del producto
    y la cantidad disponible de stock.
    """
    sku: str = Field(
        alias="product_reference_code",
        description="SKU del producto (debe coincidir con Shopify)",
        min_length=1
    )
    quantity: int = Field(
        alias="available_quantity",
        description="Cantidad total disponible en Odoo",
        ge=0
    )
    location_id: int | None = Field(
        default=None,
        alias="location_id",
        description="ID de ubicación en Odoo (opcional, para logging)"
    )

    class Config:
        """Configuración del modelo"""
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "product_reference_code": "MANT-KAR-500",
                "available_quantity": 25,
                "location_id": 8
            }
        }

    @field_validator('sku')
    @classmethod
    def validate_sku(cls, v: str) -> str:
        """Validar que el SKU no esté vacío después de strip"""
        if not v.strip():
            raise ValueError("SKU no puede estar vacío")
        return v.strip()


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


class WebhookResponse(BaseModel):
    """
    Modelo para la respuesta del webhook.
    """
    success: bool = Field(description="Indica si la operación fue exitosa")
    message: str = Field(description="Mensaje descriptivo del resultado")
    sku: str | None = Field(default=None, description="SKU procesado")
    quantity_updated: int | None = Field(default=None, description="Cantidad actualizada")
    delta: int | None = Field(default=None, description="Ajuste aplicado")
