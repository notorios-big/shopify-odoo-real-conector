"""
CLI para ejecutar sincronización de inventario desde línea de comandos.
"""
import sys
import logging
from typing import Optional

from .sync_service import SyncService
from .odoo_client import OdooConnectionError
from .config import settings

# Configurar logging para CLI
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_connections():
    """Prueba las conexiones con Odoo y Shopify"""
    print("\n" + "=" * 60)
    print("PROBANDO CONEXIONES")
    print("=" * 60 + "\n")

    sync_service = SyncService()
    result = sync_service.test_connections()

    # Mostrar resultado de Odoo
    odoo_status = result["odoo"]
    print(f"ODOO ({settings.ODOO_URL}):")
    print(f"  Estado: {odoo_status['status']}")
    print(f"  Mensaje: {odoo_status['message']}")
    print()

    # Mostrar resultado de Shopify
    shopify_status = result["shopify"]
    print(f"SHOPIFY ({settings.SHOPIFY_STORE_URL}):")
    print(f"  Estado: {shopify_status['status']}")
    print(f"  Mensaje: {shopify_status['message']}")
    print()

    # Mostrar resultado general
    overall = result["overall"]
    print("-" * 60)
    print(f"RESULTADO GENERAL: {overall}")
    print("-" * 60)

    return 0 if overall == "OK" else 1


def sync_inventory(verbose: bool = False):
    """Ejecuta la sincronización de inventario"""
    print("\n" + "=" * 60)
    print("SINCRONIZACIÓN DE INVENTARIO ODOO → SHOPIFY")
    print("=" * 60 + "\n")

    print(f"Ubicación de Odoo: {settings.ODOO_LOCATION_ID}")
    print(f"Tienda Shopify: {settings.SHOPIFY_STORE_URL}")
    print()

    try:
        sync_service = SyncService()
        summary = sync_service.sync_all_inventory()

        print("\n" + "=" * 60)
        print("RESUMEN DE SINCRONIZACIÓN")
        print("=" * 60 + "\n")

        print(f"Total de productos procesados: {summary.total_products}")
        print(f"Exitosos:                       {summary.successful}")
        print(f"Fallidos:                       {summary.failed}")
        print(f"Omitidos (sin SKU):             {summary.skipped}")
        print()

        if verbose and summary.results:
            print("\n" + "-" * 60)
            print("DETALLES POR PRODUCTO")
            print("-" * 60 + "\n")

            for result in summary.results:
                status_icon = "✓" if result.success else "✗"
                print(f"{status_icon} SKU: {result.sku}")
                print(f"  Mensaje: {result.message}")
                if result.quantity_updated is not None:
                    print(f"  Cantidad: {result.quantity_updated} (delta: {result.delta})")
                print()

        # Mostrar productos fallidos si hay
        if summary.failed > 0 and not verbose:
            print("\n" + "-" * 60)
            print("PRODUCTOS FALLIDOS")
            print("-" * 60 + "\n")

            failed_results = [r for r in summary.results if not r.success]
            for result in failed_results:
                print(f"✗ SKU: {result.sku}")
                print(f"  Error: {result.message}")
                print()

        print("=" * 60)
        print(f"SINCRONIZACIÓN COMPLETADA: {summary.successful}/{summary.total_products} exitosos")
        print("=" * 60 + "\n")

        return 0 if summary.failed == 0 else 1

    except OdooConnectionError as e:
        print(f"\n❌ ERROR DE CONEXIÓN CON ODOO:")
        print(f"   {e}")
        print()
        return 1

    except Exception as e:
        print(f"\n❌ ERROR INESPERADO:")
        print(f"   {e}")
        logger.exception("Error durante sincronización")
        print()
        return 1


def main():
    """Punto de entrada del CLI"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Conector de stock Odoo-Shopify",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  %(prog)s sync              Sincronizar inventario
  %(prog)s sync --verbose    Sincronizar con detalles
  %(prog)s test              Probar conexiones
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Comando a ejecutar')

    # Comando 'sync'
    sync_parser = subparsers.add_parser('sync', help='Sincronizar inventario')
    sync_parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Mostrar detalles de cada producto'
    )

    # Comando 'test'
    subparsers.add_parser('test', help='Probar conexiones con Odoo y Shopify')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    if args.command == 'test':
        return test_connections()
    elif args.command == 'sync':
        return sync_inventory(verbose=args.verbose)

    return 0


if __name__ == "__main__":
    sys.exit(main())
