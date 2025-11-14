"""
Servicio de Shopify para sincronización de inventario vía GraphQL API.
"""
import logging
import time
from typing import Optional, List, Dict, Tuple
import requests

from .models import ShopifyInventoryUpdate, BulkInventoryAdjustment
from .config import settings

logger = logging.getLogger(__name__)


class RateLimitExceeded(Exception):
    """Excepción para cuando se excede el rate limit"""
    pass


class ShopifyGraphQLError(Exception):
    """Excepción personalizada para errores de GraphQL"""
    pass


class ShopifyService:
    """
    Servicio para interactuar con la API GraphQL de Shopify.

    Este servicio maneja:
    1. Obtención de ubicaciones (locations)
    2. Búsqueda de productos por SKU
    3. Ajuste de inventario
    """

    # --- Consultas y Mutaciones GraphQL ---

    GET_LOCATION_QUERY = """
    query getFirstLocation {
      locations(first: 1) {
        edges {
          node {
            id
            name
          }
        }
      }
    }
    """

    GET_VARIANT_BY_SKU_QUERY = """
    query getVariantData($sku: String!) {
      productVariants(first: 1, query: $sku) {
        edges {
          node {
            id
            sku
            inventoryItem {
              id
              inventoryLevels(first: 50) {
                edges {
                  node {
                    location {
                      id
                    }
                    quantities(names: ["available"]) {
                      quantity
                    }
                  }
                }
              }
            }
          }
        }
      }
    }
    """

    ADJUST_INVENTORY_MUTATION = """
    mutation adjustInventory($inventoryItemID: ID!, $locationID: ID!, $delta: Int!) {
      inventoryAdjustQuantities(
        input: {
          reason: "correction"
          name: "available"
          changes: [
            {
              inventoryItemId: $inventoryItemID
              locationId: $locationID
              delta: $delta
            }
          ]
        }
      ) {
        inventoryAdjustmentGroup {
          id
        }
        userErrors {
          field
          message
        }
      }
    }
    """

    BULK_ADJUST_INVENTORY_MUTATION = """
    mutation BulkUpdateInventory($adjustments: [InventoryAdjustItemInput!]!, $locationId: ID!) {
      inventoryBulkAdjustQuantityAtLocation(
        inventoryItemAdjustments: $adjustments
        locationId: $locationId
      ) {
        inventoryLevels {
          id
          available
          item {
            id
            sku
          }
        }
        userErrors {
          field
          message
        }
      }
    }
    """

    # Constantes para rate limiting y batching
    MAX_BATCH_SIZE = 250  # Máximo de items por batch según Shopify
    MAX_RETRIES = 4  # Máximo de reintentos
    INITIAL_BACKOFF = 1  # Backoff inicial en segundos

    def __init__(self):
        """Inicializa el servicio de Shopify"""
        self.graphql_endpoint = (
            f"{settings.SHOPIFY_STORE_URL}/admin/api/"
            f"{settings.SHOPIFY_API_VERSION}/graphql.json"
        )
        self.headers = {
            'X-Shopify-Access-Token': settings.SHOPIFY_ACCESS_TOKEN,
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        self._cached_location_id: Optional[str] = None
        self.total_api_calls = 0
        self.total_retries = 0

    def _run_query(self, query: str, variables: dict, retry_count: int = 0) -> Tuple[dict, dict]:
        """
        Ejecuta una consulta o mutación GraphQL con retry automático.

        Args:
            query: La consulta o mutación GraphQL
            variables: Variables para la consulta
            retry_count: Número de reintentos realizados

        Returns:
            Tuple[dict, dict]: (datos de respuesta, información de extensiones/throttle)

        Raises:
            ShopifyGraphQLError: Si hay errores en la respuesta o la petición falla
            RateLimitExceeded: Si se excede el rate limit después de todos los reintentos
        """
        payload = {'query': query, 'variables': variables}
        logger.debug(f"Ejecutando GraphQL query (intento {retry_count + 1}): {query[:100]}...")

        try:
            self.total_api_calls += 1
            response = requests.post(
                self.graphql_endpoint,
                headers=self.headers,
                json=payload,
                timeout=60  # Aumentado para bulk operations
            )

            # Manejar throttling (429)
            if response.status_code == 429:
                if retry_count < self.MAX_RETRIES:
                    backoff_time = self.INITIAL_BACKOFF * (2 ** retry_count)
                    logger.warning(f"Rate limit alcanzado. Esperando {backoff_time}s antes de reintentar...")
                    self.total_retries += 1
                    time.sleep(backoff_time)
                    return self._run_query(query, variables, retry_count + 1)
                else:
                    raise RateLimitExceeded("Se excedió el rate limit después de todos los reintentos")

            response.raise_for_status()
            data = response.json()

            # Extraer información de throttling/cost de extensions
            extensions = data.get('extensions', {})
            throttle_status = extensions.get('cost', {})

            if throttle_status:
                logger.debug(
                    f"GraphQL Cost - Requested: {throttle_status.get('requestedQueryCost', 'N/A')}, "
                    f"Available: {throttle_status.get('throttleStatus', {}).get('currentlyAvailable', 'N/A')}, "
                    f"Restore Rate: {throttle_status.get('throttleStatus', {}).get('restoreRate', 'N/A')}/s"
                )

            if 'errors' in data:
                error_msg = f"GraphQL errors: {data['errors']}"
                logger.error(error_msg)

                # Verificar si es un error de throttling
                if any('throttled' in str(err).lower() for err in data['errors']):
                    if retry_count < self.MAX_RETRIES:
                        backoff_time = self.INITIAL_BACKOFF * (2 ** retry_count)
                        logger.warning(f"Throttled. Esperando {backoff_time}s antes de reintentar...")
                        self.total_retries += 1
                        time.sleep(backoff_time)
                        return self._run_query(query, variables, retry_count + 1)

                raise ShopifyGraphQLError(error_msg)

            return data.get('data', {}), extensions

        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP error: {e}, Response: {response.text}"
            logger.error(error_msg)

            # Reintentar en errores 5xx
            if response.status_code >= 500 and retry_count < self.MAX_RETRIES:
                backoff_time = self.INITIAL_BACKOFF * (2 ** retry_count)
                logger.warning(f"Error de servidor. Esperando {backoff_time}s antes de reintentar...")
                self.total_retries += 1
                time.sleep(backoff_time)
                return self._run_query(query, variables, retry_count + 1)

            raise ShopifyGraphQLError(error_msg)

        except requests.exceptions.RequestException as e:
            error_msg = f"Request error: {e}"
            logger.error(error_msg)

            # Reintentar en errores de red
            if retry_count < self.MAX_RETRIES:
                backoff_time = self.INITIAL_BACKOFF * (2 ** retry_count)
                logger.warning(f"Error de red. Esperando {backoff_time}s antes de reintentar...")
                self.total_retries += 1
                time.sleep(backoff_time)
                return self._run_query(query, variables, retry_count + 1)

            raise ShopifyGraphQLError(error_msg)

    def get_location_id(self) -> str:
        """
        Obtiene el ID de la primera ubicación en Shopify.

        Utiliza un caché simple para evitar consultas repetidas.

        Returns:
            str: ID de la ubicación (formato: gid://shopify/Location/...)

        Raises:
            ShopifyGraphQLError: Si no se encuentra ninguna ubicación
        """
        if self._cached_location_id:
            logger.debug(f"Usando location_id cacheado: {self._cached_location_id}")
            return self._cached_location_id

        logger.info("Obteniendo ubicación de Shopify...")
        data, _ = self._run_query(self.GET_LOCATION_QUERY, {})

        edges = data.get('locations', {}).get('edges', [])
        if not edges:
            raise ShopifyGraphQLError("No se encontraron ubicaciones en Shopify")

        location = edges[0]['node']
        self._cached_location_id = location['id']
        logger.info(f"Ubicación obtenida: {location['name']} (ID: {self._cached_location_id})")

        return self._cached_location_id

    def get_variant_data_by_sku(self, sku: str, location_id: str) -> Optional[ShopifyInventoryUpdate]:
        """
        Obtiene los datos de inventario de una variante por SKU.

        Args:
            sku: SKU del producto
            location_id: ID de la ubicación en Shopify

        Returns:
            ShopifyInventoryUpdate si se encuentra el producto, None si no existe

        Raises:
            ShopifyGraphQLError: Si hay errores en la consulta
        """
        logger.info(f"Buscando variante con SKU: {sku}")

        # Construir query de búsqueda (buscar por SKU exacto)
        search_query = f"sku:{sku}"
        variables = {"sku": search_query}

        data, _ = self._run_query(self.GET_VARIANT_BY_SKU_QUERY, variables)

        edges = data.get('productVariants', {}).get('edges', [])
        if not edges:
            logger.warning(f"No se encontró variante con SKU: {sku}")
            return None

        variant = edges[0]['node']
        inventory_item_id = variant['inventoryItem']['id']
        logger.info(f"Variante encontrada - ID: {variant['id']}, Inventory Item: {inventory_item_id}")

        # Buscar el stock actual para la ubicación específica
        current_quantity = 0
        inventory_levels = variant['inventoryItem']['inventoryLevels']['edges']

        for level_edge in inventory_levels:
            level = level_edge['node']
            if level['location']['id'] == location_id:
                if level['quantities']:
                    current_quantity = level['quantities'][0]['quantity']
                break

        logger.info(f"Stock actual en Shopify para SKU {sku}: {current_quantity}")

        return ShopifyInventoryUpdate(
            inventory_item_id=inventory_item_id,
            location_id=location_id,
            current_quantity=current_quantity,
            new_quantity=current_quantity,  # Se actualizará después
            delta=0  # Se calculará después
        )

    def adjust_inventory(self, inventory_update: ShopifyInventoryUpdate) -> bool:
        """
        Ajusta el inventario en Shopify.

        Args:
            inventory_update: Datos de la actualización de inventario

        Returns:
            bool: True si el ajuste fue exitoso

        Raises:
            ShopifyGraphQLError: Si hay errores en la mutación
        """
        if not inventory_update.needs_adjustment:
            logger.info("No se requiere ajuste de inventario (delta = 0)")
            return True

        logger.info(
            f"Ajustando inventario: {inventory_update.current_quantity} -> "
            f"{inventory_update.new_quantity} (delta: {inventory_update.delta})"
        )

        variables = {
            "inventoryItemID": inventory_update.inventory_item_id,
            "locationID": inventory_update.location_id,
            "delta": inventory_update.delta
        }

        data, _ = self._run_query(self.ADJUST_INVENTORY_MUTATION, variables)

        user_errors = data.get('inventoryAdjustQuantities', {}).get('userErrors', [])
        if user_errors:
            error_msg = f"Errores al ajustar inventario: {user_errors}"
            logger.error(error_msg)
            raise ShopifyGraphQLError(error_msg)

        logger.info("Inventario ajustado exitosamente")
        return True

    def sync_stock(self, sku: str, new_quantity: int) -> dict:
        """
        Sincroniza el stock de un producto desde Odoo a Shopify.

        Este es el método principal que orquesta todo el flujo:
        1. Obtener ubicación
        2. Buscar producto por SKU
        3. Calcular delta
        4. Ajustar inventario

        Args:
            sku: SKU del producto
            new_quantity: Nueva cantidad desde Odoo

        Returns:
            dict con el resultado de la sincronización

        Raises:
            ShopifyGraphQLError: Si hay errores en cualquier paso
        """
        logger.info(f"Iniciando sincronización de stock para SKU: {sku}, cantidad: {new_quantity}")

        try:
            # Paso 1: Obtener ubicación
            location_id = self.get_location_id()

            # Paso 2: Obtener datos de la variante
            variant_data = self.get_variant_data_by_sku(sku, location_id)

            if not variant_data:
                return {
                    "success": False,
                    "message": f"Producto con SKU '{sku}' no encontrado en Shopify",
                    "sku": sku
                }

            # Paso 3: Calcular delta
            variant_data.new_quantity = new_quantity
            variant_data.delta = new_quantity - variant_data.current_quantity

            # Paso 4: Ajustar inventario
            self.adjust_inventory(variant_data)

            return {
                "success": True,
                "message": f"Stock sincronizado exitosamente para SKU '{sku}'",
                "sku": sku,
                "quantity_updated": new_quantity,
                "delta": variant_data.delta
            }

        except ShopifyGraphQLError as e:
            logger.error(f"Error al sincronizar stock para SKU {sku}: {e}")
            return {
                "success": False,
                "message": f"Error al sincronizar: {str(e)}",
                "sku": sku
            }

    def bulk_adjust_inventory(
        self,
        adjustments: List['BulkInventoryAdjustment'],
        location_id: str
    ) -> 'BulkUpdateResult':
        """
        Ajusta el inventario de múltiples items en una sola llamada (bulk).

        Args:
            adjustments: Lista de ajustes de inventario (máximo 250)
            location_id: ID de la ubicación en Shopify

        Returns:
            BulkUpdateResult con el resultado de la operación

        Raises:
            ShopifyGraphQLError: Si hay errores en la mutación
        """
        from .models import BulkUpdateResult

        if len(adjustments) > self.MAX_BATCH_SIZE:
            raise ValueError(f"Máximo {self.MAX_BATCH_SIZE} items por batch, recibidos: {len(adjustments)}")

        if not adjustments:
            logger.warning("No hay ajustes para procesar")
            return BulkUpdateResult(
                success=True,
                items_updated=0,
                items_failed=0,
                user_errors=[],
                throttle_status=None
            )

        logger.info(f"Ajustando inventario en bulk: {len(adjustments)} items")

        # Preparar variables para la mutación
        # Filtrar solo los ajustes con delta != 0
        filtered_adjustments = [adj for adj in adjustments if adj.available_delta != 0]

        if not filtered_adjustments:
            logger.info("Todos los deltas son 0, no se requiere ajuste")
            return BulkUpdateResult(
                success=True,
                items_updated=0,
                items_failed=0,
                user_errors=[],
                throttle_status=None
            )

        # Construir input para la mutación
        adjustment_inputs = [
            {
                "inventoryItemId": adj.inventory_item_id,
                "availableDelta": adj.available_delta
            }
            for adj in filtered_adjustments
        ]

        variables = {
            "adjustments": adjustment_inputs,
            "locationId": location_id
        }

        try:
            start_time = time.time()
            data, extensions = self._run_query(self.BULK_ADJUST_INVENTORY_MUTATION, variables)
            elapsed_time = time.time() - start_time

            logger.info(f"Bulk mutation completada en {elapsed_time:.2f}s")

            # Procesar respuesta
            bulk_result = data.get('inventoryBulkAdjustQuantityAtLocation', {})
            inventory_levels = bulk_result.get('inventoryLevels', [])
            user_errors = bulk_result.get('userErrors', [])

            # Extraer throttle status
            throttle_status = extensions.get('cost', {}).get('throttleStatus', {}) if extensions else None

            items_updated = len(inventory_levels)
            items_failed = len(filtered_adjustments) - items_updated

            if user_errors:
                logger.warning(f"Errores en bulk update: {user_errors}")

            result = BulkUpdateResult(
                success=len(user_errors) == 0,
                items_updated=items_updated,
                items_failed=items_failed,
                user_errors=user_errors,
                throttle_status=throttle_status
            )

            logger.info(
                f"Bulk update: {items_updated} exitosos, {items_failed} fallidos, "
                f"{len(user_errors)} errores"
            )

            return result

        except (ShopifyGraphQLError, RateLimitExceeded) as e:
            logger.error(f"Error en bulk adjust inventory: {e}")
            return BulkUpdateResult(
                success=False,
                items_updated=0,
                items_failed=len(filtered_adjustments),
                user_errors=[{"message": str(e)}],
                throttle_status=None
            )

    def create_batches(
        self,
        adjustments: List['BulkInventoryAdjustment'],
        batch_size: int = None
    ) -> List[List['BulkInventoryAdjustment']]:
        """
        Divide una lista de ajustes en batches de tamaño máximo.

        Args:
            adjustments: Lista de ajustes
            batch_size: Tamaño máximo de cada batch (default: MAX_BATCH_SIZE)

        Returns:
            Lista de batches
        """
        if batch_size is None:
            batch_size = self.MAX_BATCH_SIZE

        batches = []
        for i in range(0, len(adjustments), batch_size):
            batch = adjustments[i:i + batch_size]
            batches.append(batch)

        logger.info(f"Creados {len(batches)} batches de hasta {batch_size} items")
        return batches

    def get_stats(self) -> dict:
        """
        Obtiene estadísticas de uso del servicio.

        Returns:
            dict con estadísticas
        """
        return {
            "total_api_calls": self.total_api_calls,
            "total_retries": self.total_retries,
            "cached_location_id": self._cached_location_id
        }
