"""
Servicio de sincronización entre Odoo y Shopify.
"""
import logging
import time
from typing import List

from .odoo_client import OdooClient, OdooConnectionError
from .shopify_service import ShopifyService, ShopifyGraphQLError
from .models import OdooStockQuant, SyncResult, SyncSummary, BulkInventoryAdjustment
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

    def sync_all_inventory_bulk(self) -> SyncSummary:
        """
        Sincroniza todo el inventario usando actualización masiva (bulk).

        Este método es más eficiente que sync_all_inventory ya que:
        1. Agrupa productos en batches de hasta 250 items
        2. Hace una sola llamada GraphQL por batch
        3. Respeta los rate limits con retry automático

        Returns:
            SyncSummary con el resultado de la sincronización

        Raises:
            OdooConnectionError: Si hay error al conectar con Odoo
        """
        start_time = time.time()
        logger.info(f"Iniciando sincronización BULK de inventario desde ubicación {settings.ODOO_LOCATION_ID}")

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
                results=[],
                bulk_mode=True,
                total_batches=0,
                total_time_seconds=0.0
            )

        logger.info(f"Se obtuvieron {len(stock_quants)} productos de Odoo.")

        # Obtener ubicación de Shopify
        try:
            shopify_location_id = self.shopify_service.get_location_id()
        except Exception as e:
            logger.error(f"Error al obtener ubicación de Shopify: {e}")
            raise

        # Preparar ajustes (buscar inventory_item_id para cada SKU)
        logger.info("Obteniendo IDs de inventario de Shopify...")
        adjustments = []
        results = []
        skipped = 0

        for stock_quant in stock_quants:
            try:
                # Buscar el producto en Shopify por SKU
                variant_data = self.shopify_service.get_variant_data_by_sku(
                    stock_quant.sku,
                    shopify_location_id
                )

                if not variant_data:
                    logger.warning(f"SKU '{stock_quant.sku}' no encontrado en Shopify. Omitiendo.")
                    skipped += 1
                    results.append(SyncResult(
                        success=False,
                        message=f"SKU no encontrado en Shopify",
                        sku=stock_quant.sku
                    ))
                    continue

                # Calcular delta
                new_quantity = int(stock_quant.quantity)
                delta = new_quantity - variant_data.current_quantity

                # Crear ajuste
                adjustment = BulkInventoryAdjustment(
                    inventory_item_id=variant_data.inventory_item_id,
                    available_delta=delta,
                    sku=stock_quant.sku
                )
                adjustments.append(adjustment)

            except Exception as e:
                logger.error(f"Error al preparar SKU '{stock_quant.sku}': {e}")
                skipped += 1
                results.append(SyncResult(
                    success=False,
                    message=f"Error al preparar: {str(e)}",
                    sku=stock_quant.sku
                ))

        logger.info(f"Preparados {len(adjustments)} ajustes. {skipped} omitidos.")

        if not adjustments:
            elapsed_time = time.time() - start_time
            return SyncSummary(
                total_products=len(stock_quants),
                successful=0,
                failed=0,
                skipped=skipped,
                results=results,
                bulk_mode=True,
                total_batches=0,
                total_time_seconds=elapsed_time
            )

        # Crear batches de hasta 250 items
        batches = self.shopify_service.create_batches(adjustments)
        logger.info(f"Procesando {len(batches)} batches...")

        successful = 0
        failed = 0

        for batch_num, batch in enumerate(batches, 1):
            logger.info(f"Procesando batch {batch_num}/{len(batches)} ({len(batch)} items)...")

            try:
                bulk_result = self.shopify_service.bulk_adjust_inventory(
                    batch,
                    shopify_location_id
                )

                # Actualizar contadores
                successful += bulk_result.items_updated
                failed += bulk_result.items_failed

                # Agregar resultados individuales
                for adj in batch:
                    if bulk_result.success:
                        results.append(SyncResult(
                            success=True,
                            message="Actualizado en batch",
                            sku=adj.sku,
                            delta=adj.available_delta
                        ))
                    else:
                        results.append(SyncResult(
                            success=False,
                            message=f"Error en batch: {bulk_result.user_errors}",
                            sku=adj.sku
                        ))

                # Log throttle status si está disponible
                if bulk_result.throttle_status:
                    available = bulk_result.throttle_status.get('currentlyAvailable', 'N/A')
                    logger.info(f"Rate limit disponible: {available}")

            except Exception as e:
                logger.error(f"Error al procesar batch {batch_num}: {e}")
                failed += len(batch)
                for adj in batch:
                    results.append(SyncResult(
                        success=False,
                        message=f"Error en batch: {str(e)}",
                        sku=adj.sku
                    ))

        elapsed_time = time.time() - start_time

        # Obtener estadísticas del servicio
        stats = self.shopify_service.get_stats()
        logger.info(
            f"Sincronización BULK completada en {elapsed_time:.2f}s: "
            f"{successful}/{len(stock_quants)} exitosos, {failed} fallidos, {skipped} omitidos. "
            f"API calls: {stats['total_api_calls']}, Retries: {stats['total_retries']}"
        )

        summary = SyncSummary(
            total_products=len(stock_quants),
            successful=successful,
            failed=failed,
            skipped=skipped,
            results=results,
            bulk_mode=True,
            total_batches=len(batches),
            total_time_seconds=elapsed_time
        )

        return summary
