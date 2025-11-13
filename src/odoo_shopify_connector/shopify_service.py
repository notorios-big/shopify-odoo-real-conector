"""
Servicio de Shopify para sincronización de inventario vía GraphQL API.
"""
import logging
from typing import Optional
import requests

from .models import ShopifyInventoryUpdate
from .config import settings

logger = logging.getLogger(__name__)


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

    def _run_query(self, query: str, variables: dict) -> dict:
        """
        Ejecuta una consulta o mutación GraphQL.

        Args:
            query: La consulta o mutación GraphQL
            variables: Variables para la consulta

        Returns:
            dict: Datos de respuesta

        Raises:
            ShopifyGraphQLError: Si hay errores en la respuesta o la petición falla
        """
        payload = {'query': query, 'variables': variables}
        logger.debug(f"Ejecutando GraphQL query: {query[:100]}...")

        try:
            response = requests.post(
                self.graphql_endpoint,
                headers=self.headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()

            if 'errors' in data:
                error_msg = f"GraphQL errors: {data['errors']}"
                logger.error(error_msg)
                raise ShopifyGraphQLError(error_msg)

            return data.get('data', {})

        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP error: {e}, Response: {response.text}"
            logger.error(error_msg)
            raise ShopifyGraphQLError(error_msg)
        except requests.exceptions.RequestException as e:
            error_msg = f"Request error: {e}"
            logger.error(error_msg)
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
        data = self._run_query(self.GET_LOCATION_QUERY, {})

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

        data = self._run_query(self.GET_VARIANT_BY_SKU_QUERY, variables)

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

        data = self._run_query(self.ADJUST_INVENTORY_MUTATION, variables)

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
