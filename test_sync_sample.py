"""
Script de prueba para sincronizar un subset de productos.

Este script permite probar la sincronización con un número limitado de productos
antes de ejecutar una sincronización completa.

Uso:
    python test_sync_sample.py --limit 5                    # Probar con 5 productos
    python test_sync_sample.py --limit 10 --dry-run        # Dry-run con 10 productos
    python test_sync_sample.py --skus PROD-001 PROD-002    # Probar SKUs específicos
"""

import sys
import logging
import argparse
from typing import List, Optional
from pathlib import Path

# Agregar src al path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from odoo_shopify_connector.odoo_client import OdooClient, OdooConnectionError
from odoo_shopify_connector.shopify_service import ShopifyService, ShopifyGraphQLError
from odoo_shopify_connector.models import OdooStockQuant, SyncResult
from odoo_shopify_connector.config import settings

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SampleSyncTester:
    """Clase para probar sincronización con subset de productos"""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.odoo_client = OdooClient()
        self.shopify_service = ShopifyService()

    def test_connections(self) -> bool:
        """Prueba las conexiones con Odoo y Shopify"""
        print("\n" + "=" * 70)
        print("🔍 PROBANDO CONEXIONES")
        print("=" * 70 + "\n")

        # Probar Odoo
        try:
            odoo_ok = self.odoo_client.test_connection()
            if odoo_ok:
                print("✓ Odoo:    CONECTADO")
            else:
                print("✗ Odoo:    ERROR de autenticación")
                return False
        except Exception as e:
            print(f"✗ Odoo:    ERROR - {e}")
            return False

        # Probar Shopify
        try:
            location_id = self.shopify_service.get_location_id()
            print(f"✓ Shopify: CONECTADO (Location: {location_id})")
        except Exception as e:
            print(f"✗ Shopify: ERROR - {e}")
            return False

        print()
        return True

    def get_sample_products(
        self,
        limit: Optional[int] = None,
        specific_skus: Optional[List[str]] = None
    ) -> List[OdooStockQuant]:
        """
        Obtiene un subset de productos de Odoo.

        Args:
            limit: Número máximo de productos a obtener
            specific_skus: Lista de SKUs específicos a buscar

        Returns:
            Lista de productos
        """
        print("=" * 70)
        print("📦 OBTENIENDO PRODUCTOS DE ODOO")
        print("=" * 70 + "\n")

        try:
            all_products = self.odoo_client.get_inventory_by_location(settings.ODOO_LOCATION_ID)

            if not all_products:
                print("❌ No se encontraron productos en Odoo")
                return []

            print(f"Total productos en ubicación {settings.ODOO_LOCATION_ID}: {len(all_products)}")

            # Filtrar por SKUs específicos si se proporcionan
            if specific_skus:
                products = [p for p in all_products if p.sku in specific_skus]
                print(f"Productos con SKUs especificados: {len(products)}")

                # Mostrar cuáles no se encontraron
                found_skus = {p.sku for p in products}
                missing_skus = set(specific_skus) - found_skus
                if missing_skus:
                    print(f"⚠️  SKUs no encontrados: {', '.join(missing_skus)}")
            else:
                # Tomar los primeros N productos
                products = all_products[:limit] if limit else all_products
                print(f"Productos seleccionados para prueba: {len(products)}")

            print()
            return products

        except OdooConnectionError as e:
            print(f"❌ Error al conectar con Odoo: {e}")
            return []

    def preview_sync(self, products: List[OdooStockQuant]):
        """Muestra un preview de qué se sincronizará"""
        print("=" * 70)
        print("👀 PREVIEW DE SINCRONIZACIÓN")
        print("=" * 70 + "\n")

        if not products:
            print("❌ No hay productos para sincronizar")
            return

        print(f"Se sincronizarán {len(products)} productos:\n")

        # Mostrar tabla de productos
        print(f"{'SKU':<20} {'Nombre':<30} {'Cantidad':>10}")
        print("-" * 70)

        for product in products:
            sku = product.sku[:20]
            name = product.product_name[:30]
            qty = int(product.quantity)
            print(f"{sku:<20} {name:<30} {qty:>10}")

        print()

    def sync_products(self, products: List[OdooStockQuant]) -> List[SyncResult]:
        """
        Sincroniza los productos con Shopify.

        Args:
            products: Lista de productos a sincronizar

        Returns:
            Lista de resultados
        """
        if self.dry_run:
            print("=" * 70)
            print("🔍 MODO DRY-RUN (No se escribirá a Shopify)")
            print("=" * 70 + "\n")
        else:
            print("=" * 70)
            print("🚀 INICIANDO SINCRONIZACIÓN")
            print("=" * 70 + "\n")

        results = []
        shopify_location_id = self.shopify_service.get_location_id()

        for i, product in enumerate(products, 1):
            print(f"[{i}/{len(products)}] Procesando SKU: {product.sku}")

            try:
                # Buscar el producto en Shopify
                variant_data = self.shopify_service.get_variant_data_by_sku(
                    product.sku,
                    shopify_location_id
                )

                if not variant_data:
                    print(f"  ⚠️  No encontrado en Shopify")
                    results.append(SyncResult(
                        success=False,
                        message="SKU no encontrado en Shopify",
                        sku=product.sku
                    ))
                    continue

                # Calcular delta
                new_quantity = int(product.quantity)
                current_quantity = variant_data.current_quantity
                delta = new_quantity - current_quantity

                print(f"  Actual: {current_quantity} → Nuevo: {new_quantity} (Δ {delta:+d})")

                if self.dry_run:
                    # En modo dry-run, solo mostrar qué haría
                    if delta == 0:
                        print(f"  ℹ️  Sin cambios necesarios")
                    else:
                        print(f"  ✓ DRY-RUN: Se ajustaría en {delta:+d}")

                    results.append(SyncResult(
                        success=True,
                        message=f"DRY-RUN: Delta {delta:+d}",
                        sku=product.sku,
                        quantity_updated=new_quantity,
                        delta=delta
                    ))
                else:
                    # Sincronizar realmente
                    if delta == 0:
                        print(f"  ℹ️  Sin cambios necesarios")
                        results.append(SyncResult(
                            success=True,
                            message="Sin cambios",
                            sku=product.sku,
                            quantity_updated=new_quantity,
                            delta=0
                        ))
                    else:
                        variant_data.new_quantity = new_quantity
                        variant_data.delta = delta
                        self.shopify_service.adjust_inventory(variant_data)
                        print(f"  ✓ Sincronizado exitosamente")

                        results.append(SyncResult(
                            success=True,
                            message="Sincronizado",
                            sku=product.sku,
                            quantity_updated=new_quantity,
                            delta=delta
                        ))

            except ShopifyGraphQLError as e:
                print(f"  ✗ Error de Shopify: {e}")
                results.append(SyncResult(
                    success=False,
                    message=f"Error de Shopify: {str(e)}",
                    sku=product.sku
                ))
            except Exception as e:
                print(f"  ✗ Error inesperado: {e}")
                results.append(SyncResult(
                    success=False,
                    message=f"Error: {str(e)}",
                    sku=product.sku
                ))

            print()

        return results

    def print_summary(self, results: List[SyncResult]):
        """Imprime resumen de resultados"""
        print("=" * 70)
        print("📊 RESUMEN DE RESULTADOS")
        print("=" * 70 + "\n")

        successful = sum(1 for r in results if r.success)
        failed = sum(1 for r in results if not r.success)
        no_changes = sum(1 for r in results if r.success and r.delta == 0)
        updated = sum(1 for r in results if r.success and r.delta != 0)

        print(f"Total procesados:  {len(results)}")
        print(f"Exitosos:          {successful}")
        print(f"Fallidos:          {failed}")
        print(f"Sin cambios:       {no_changes}")
        print(f"Actualizados:      {updated}")
        print()

        # Mostrar detalles de fallidos
        if failed > 0:
            print("❌ PRODUCTOS FALLIDOS:")
            print("-" * 70)
            for result in results:
                if not result.success:
                    print(f"  SKU: {result.sku}")
                    print(f"  Error: {result.message}")
                    print()

        # Mostrar productos actualizados
        if updated > 0 and not self.dry_run:
            print("✓ PRODUCTOS ACTUALIZADOS:")
            print("-" * 70)
            for result in results:
                if result.success and result.delta != 0:
                    print(f"  SKU: {result.sku} (Δ {result.delta:+d})")
            print()


def main():
    """Función principal"""
    parser = argparse.ArgumentParser(
        description="Script de prueba para sincronizar un subset de productos",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos de uso:

  # Probar con los primeros 5 productos
  python test_sync_sample.py --limit 5

  # Dry-run con 10 productos (sin escribir a Shopify)
  python test_sync_sample.py --limit 10 --dry-run

  # Probar SKUs específicos
  python test_sync_sample.py --skus PROD-001 PROD-002 PROD-003

  # Dry-run con SKUs específicos
  python test_sync_sample.py --skus PROD-001 PROD-002 --dry-run

  # Probar todos los productos (¡cuidado!)
  python test_sync_sample.py --all --dry-run
        """
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        '--limit',
        type=int,
        help='Número de productos a probar (toma los primeros N)'
    )
    group.add_argument(
        '--skus',
        nargs='+',
        help='SKUs específicos a probar'
    )
    group.add_argument(
        '--all',
        action='store_true',
        help='Probar con todos los productos (usar con --dry-run)'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Modo dry-run: muestra qué haría sin escribir a Shopify'
    )

    args = parser.parse_args()

    # Validación de seguridad
    if args.all and not args.dry_run:
        print("\n⚠️  ERROR: --all requiere --dry-run por seguridad")
        print("Si realmente quieres sincronizar todos los productos, usa:")
        print("  python -m odoo_shopify_connector.cli sync\n")
        return 1

    # Crear tester
    tester = SampleSyncTester(dry_run=args.dry_run)

    print("\n" + "=" * 70)
    print("🧪 TEST DE SINCRONIZACIÓN DE PRODUCTOS (SAMPLE)")
    print("=" * 70)
    print(f"\nModo: {'DRY-RUN (sin escribir)' if args.dry_run else 'REAL (escribirá a Shopify)'}")
    print(f"Odoo Location ID: {settings.ODOO_LOCATION_ID}")
    print(f"Shopify Store: {settings.SHOPIFY_STORE_URL}\n")

    # Probar conexiones
    if not tester.test_connections():
        print("❌ Error en conexiones. Abortando.")
        return 1

    # Obtener productos
    if args.skus:
        products = tester.get_sample_products(specific_skus=args.skus)
    elif args.all:
        products = tester.get_sample_products()
    else:
        products = tester.get_sample_products(limit=args.limit)

    if not products:
        print("❌ No se encontraron productos para sincronizar")
        return 1

    # Preview
    tester.preview_sync(products)

    # Confirmación si no es dry-run
    if not args.dry_run:
        print("⚠️  ATENCIÓN: Esto escribirá cambios REALES a Shopify")
        response = input("¿Continuar? (escribe 'SI' para confirmar): ")
        if response != 'SI':
            print("❌ Operación cancelada")
            return 0
        print()

    # Sincronizar
    results = tester.sync_products(products)

    # Mostrar resumen
    tester.print_summary(results)

    print("=" * 70)
    if args.dry_run:
        print("✓ DRY-RUN COMPLETADO (no se escribió nada a Shopify)")
    else:
        print("✓ SINCRONIZACIÓN COMPLETADA")
    print("=" * 70 + "\n")

    return 0 if all(r.success for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
