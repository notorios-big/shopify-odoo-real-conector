"""
Cliente para interactuar con la API XML-RPC de Odoo.
"""
import logging
import xmlrpc.client
from typing import Optional

from .models import OdooStockQuant
from .config import settings

logger = logging.getLogger(__name__)


class OdooConnectionError(Exception):
    """Excepción para errores de conexión con Odoo"""
    pass


class OdooClient:
    """
    Cliente para interactuar con la API de Odoo usando XML-RPC.

    Este cliente se conecta a Odoo para leer información de inventario.
    """

    def __init__(self):
        """Inicializa el cliente de Odoo"""
        self.url = settings.ODOO_URL
        self.db = settings.ODOO_DATABASE
        self.username = settings.ODOO_USERNAME
        self.password = settings.ODOO_PASSWORD

        self.common = xmlrpc.client.ServerProxy(f'{self.url}/xmlrpc/2/common')
        self.models = xmlrpc.client.ServerProxy(f'{self.url}/xmlrpc/2/object')

        self._uid: Optional[int] = None

    def authenticate(self) -> int:
        """
        Autentica con Odoo y retorna el UID del usuario.

        Returns:
            int: User ID en Odoo

        Raises:
            OdooConnectionError: Si falla la autenticación
        """
        if self._uid:
            logger.debug(f"Usando UID cacheado: {self._uid}")
            return self._uid

        logger.info(f"Autenticando con Odoo: {self.url}, DB: {self.db}, Usuario: {self.username}")

        try:
            self._uid = self.common.authenticate(
                self.db,
                self.username,
                self.password,
                {}
            )

            if not self._uid:
                raise OdooConnectionError("Autenticación fallida: credenciales inválidas")

            logger.info(f"Autenticación exitosa. UID: {self._uid}")
            return self._uid

        except Exception as e:
            error_msg = f"Error al autenticar con Odoo: {e}"
            logger.error(error_msg)
            raise OdooConnectionError(error_msg)

    def execute_kw(self, model: str, method: str, args: list, kwargs: dict = None):
        """
        Ejecuta un método en un modelo de Odoo.

        Args:
            model: Nombre del modelo de Odoo (ej: 'stock.quant')
            method: Método a ejecutar (ej: 'search_read')
            args: Argumentos posicionales
            kwargs: Argumentos con nombre

        Returns:
            Resultado de la llamada
        """
        uid = self.authenticate()
        kwargs = kwargs or {}

        try:
            return self.models.execute_kw(
                self.db,
                uid,
                self.password,
                model,
                method,
                args,
                kwargs
            )
        except Exception as e:
            error_msg = f"Error al ejecutar {model}.{method}: {e}"
            logger.error(error_msg)
            raise OdooConnectionError(error_msg)

    def get_inventory_by_location(self, location_id: int) -> list[OdooStockQuant]:
        """
        Obtiene todo el inventario de una ubicación específica.

        Args:
            location_id: ID de la ubicación en Odoo (ej: 28)

        Returns:
            Lista de OdooStockQuant con el inventario

        Raises:
            OdooConnectionError: Si hay error en la consulta
        """
        logger.info(f"Obteniendo inventario de ubicación {location_id}")

        # Dominio de búsqueda: ubicación específica, cantidad > 0, producto con SKU
        domain = [
            ('location_id', '=', location_id),
            ('quantity', '>', 0),
            ('product_id.default_code', '!=', False)  # Solo productos con SKU
        ]

        # Campos a leer
        fields = [
            'product_id',
            'quantity',
            'location_id'
        ]

        try:
            # Leer registros de stock.quant
            records = self.execute_kw(
                'stock.quant',
                'search_read',
                [domain],
                {'fields': fields}
            )

            logger.info(f"Se encontraron {len(records)} registros de stock en ubicación {location_id}")

            # Convertir a modelos Pydantic
            stock_quants = []
            for record in records:
                # product_id viene como tupla [id, nombre]
                product_id = record['product_id'][0] if isinstance(record['product_id'], list) else record['product_id']
                product_name = record['product_id'][1] if isinstance(record['product_id'], list) else "Unknown"

                # Obtener el SKU del producto
                sku = self._get_product_sku(product_id)

                if not sku:
                    logger.warning(f"Producto {product_name} (ID: {product_id}) no tiene SKU. Omitiendo.")
                    continue

                stock_quant = OdooStockQuant(
                    product_id=product_id,
                    product_name=product_name,
                    sku=sku,
                    quantity=record['quantity'],
                    location_id=location_id
                )
                stock_quants.append(stock_quant)

            logger.info(f"Se procesaron {len(stock_quants)} productos con SKU válido")
            return stock_quants

        except Exception as e:
            error_msg = f"Error al obtener inventario: {e}"
            logger.error(error_msg)
            raise OdooConnectionError(error_msg)

    def _get_product_sku(self, product_id: int) -> Optional[str]:
        """
        Obtiene el SKU (default_code) de un producto.

        Args:
            product_id: ID del producto en Odoo

        Returns:
            SKU del producto o None si no tiene
        """
        try:
            product = self.execute_kw(
                'product.product',
                'read',
                [[product_id]],
                {'fields': ['default_code']}
            )

            if product and product[0].get('default_code'):
                return product[0]['default_code'].strip()

            return None

        except Exception as e:
            logger.error(f"Error al obtener SKU del producto {product_id}: {e}")
            return None

    def test_connection(self) -> bool:
        """
        Prueba la conexión con Odoo.

        Returns:
            True si la conexión es exitosa
        """
        try:
            uid = self.authenticate()
            logger.info(f"✓ Conexión exitosa con Odoo. UID: {uid}")
            return True
        except Exception as e:
            logger.error(f"✗ Error al conectar con Odoo: {e}")
            return False
