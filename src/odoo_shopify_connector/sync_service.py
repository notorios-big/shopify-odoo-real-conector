"""
Servicio de sincronización entre Odoo y Shopify.
"""
import logging
from typing import List

from .odoo_client import OdooClient, OdooConnectionError
from .shopify_service import ShopifyService, ShopifyGraphQLError
from .models import OdooStockQuant, SyncResult, SyncSummary
from .config import settings

logger = logging.getLogger(__name__)


class SyncService:
    """
    Servicio que orquesta la sincronización de inventario entre Odoo y Shopify.

    Este servicio:
    1. Lee el inventario completo de Odoo (ubicación específica)
    2. Para cada producto, sincroniza el stock con Shopify
    3. Retorna un resumen de la operación
    """

    def __init__(self):
        """Inicializa el servicio de sincronización"""
        self.odoo_client = OdooClient()
        self.shopify_service = ShopifyService()

    def sync_all_inventory(self) -> SyncSummary:
        """
        Sincroniza todo el inventario de la ubicación de Odoo con Shopify.

        Returns:
            SyncSummary con el resultado de la sincronización

        Raises:
            OdooConnectionError: Si hay error al conectar con Odoo
        """
        logger.info(f"Iniciando sincronización completa de inventario desde ubicación {settings.ODOO_LOCATION_ID}")

        # Obtener inventario de Odoo
        try:
            stock_quants = self.odoo_client.get_inventory_by_location(settings.ODOO_LOCATION_ID)
        except OdooConnectionError as e:
            logger.error(f"Error al obtener inventario de Odoo: {e}")
            raise

        if not stock_quants:
            logger.warning(f"No se encontró inventario en ubicación {settings.ODOO_LOCATION_ID}")
            return SyncSummary(
                total_products=0,
                successful=0,
                failed=0,
                skipped=0,
                results=[]
            )

        logger.info(f"Se obtuvieron {len(stock_quants)} productos de Odoo. Iniciando sincronización...")

        # Sincronizar cada producto
        results = []
        successful = 0
        failed = 0

        for stock_quant in stock_quants:
            result = self._sync_single_product(stock_quant)
            results.append(result)

            if result.success:
                successful += 1
            else:
                failed += 1

        summary = SyncSummary(
            total_products=len(stock_quants),
            successful=successful,
            failed=failed,
            skipped=0,
            results=results
        )

        logger.info(
            f"Sincronización completada: {successful}/{len(stock_quants)} exitosos, "
            f"{failed} fallidos"
        )

        return summary

    def _sync_single_product(self, stock_quant: OdooStockQuant) -> SyncResult:
        """
        Sincroniza un solo producto con Shopify.

        Args:
            stock_quant: Datos del producto de Odoo

        Returns:
            SyncResult con el resultado de la sincronización
        """
        logger.info(
            f"Sincronizando producto: SKU={stock_quant.sku}, "
            f"Cantidad={stock_quant.quantity}, Nombre={stock_quant.product_name}"
        )

        try:
            # Usar el método de sync_stock del servicio de Shopify
            result = self.shopify_service.sync_stock(
                sku=stock_quant.sku,
                new_quantity=int(stock_quant.quantity)
            )

            # Convertir el dict result a SyncResult
            return SyncResult(
                success=result["success"],
                message=result["message"],
                sku=result.get("sku"),
                quantity_updated=result.get("quantity_updated"),
                delta=result.get("delta")
            )

        except ShopifyGraphQLError as e:
            logger.error(f"Error de Shopify al sincronizar SKU {stock_quant.sku}: {e}")
            return SyncResult(
                success=False,
                message=f"Error de Shopify: {str(e)}",
                sku=stock_quant.sku
            )

        except Exception as e:
            logger.exception(f"Error inesperado al sincronizar SKU {stock_quant.sku}: {e}")
            return SyncResult(
                success=False,
                message=f"Error inesperado: {str(e)}",
                sku=stock_quant.sku
            )

    def test_connections(self) -> dict:
        """
        Prueba las conexiones con Odoo y Shopify.

        Returns:
            dict con el estado de las conexiones
        """
        logger.info("Probando conexiones con Odoo y Shopify...")

        odoo_ok = False
        shopify_ok = False
        odoo_message = ""
        shopify_message = ""

        # Probar Odoo
        try:
            odoo_ok = self.odoo_client.test_connection()
            odoo_message = "Conexión exitosa" if odoo_ok else "Autenticación fallida"
        except Exception as e:
            odoo_message = f"Error: {str(e)}"

        # Probar Shopify (intentar obtener ubicación)
        try:
            location_id = self.shopify_service.get_location_id()
            shopify_ok = bool(location_id)
            shopify_message = f"Conexión exitosa. Location: {location_id}" if shopify_ok else "No se pudo obtener ubicación"
        except Exception as e:
            shopify_message = f"Error: {str(e)}"

        result = {
            "odoo": {
                "status": "OK" if odoo_ok else "ERROR",
                "message": odoo_message
            },
            "shopify": {
                "status": "OK" if shopify_ok else "ERROR",
                "message": shopify_message
            },
            "overall": "OK" if (odoo_ok and shopify_ok) else "ERROR"
        }

        logger.info(f"Test de conexiones completado: {result['overall']}")
        return result
