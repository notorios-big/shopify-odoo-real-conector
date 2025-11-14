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


def sync_inventory(verbose: bool = False, bulk: bool = True, force: bool = False):
    """Ejecuta la sincronización de inventario"""
    mode_label = "OPTIMIZADO" if bulk and not force else ("BULK COMPLETO" if bulk else "SINGLE")
    print("\n" + "=" * 60)
    print(f"SINCRONIZACIÓN {mode_label} DE INVENTARIO ODOO → SHOPIFY")
    print("=" * 60 + "\n")

    print(f"Ubicación de Odoo: {settings.ODOO_LOCATION_ID}")
    print(f"Tienda Shopify: {settings.SHOPIFY_STORE_URL}")
    print(f"Modo: {mode_label}")
    if force:
        print("⚠️  FORCE MODE: Ignorando snapshot, sincronización completa")
    print()

    try:
        sync_service = SyncService()

        # Resetear snapshot si es force mode
        if force and bulk:
            sync_service.snapshot_service.reset_snapshot()
            summary = sync_service.sync_all_inventory_bulk_with_changes()
        elif bulk:
            summary = sync_service.sync_all_inventory_bulk_with_changes()
        else:
            summary = sync_service.sync_all_inventory()

        print("\n" + "=" * 60)
        print("RESUMEN DE SINCRONIZACIÓN")
        print("=" * 60 + "\n")

        print(f"Total de productos procesados: {summary.total_products}")
        print(f"Exitosos:                       {summary.successful}")
        print(f"Fallidos:                       {summary.failed}")
        print(f"Omitidos (sin SKU):             {summary.skipped}")

        if summary.bulk_mode:
            print(f"Sin cambios:                    {summary.unchanged}")
            print(f"Nuevos:                         {summary.new}")
            print(f"Modificados:                    {summary.modified}")
            print(f"Eliminados:                     {summary.deleted}")
            print(f"Batches procesados:             {summary.total_batches}")
            print(f"Tiempo total:                   {summary.total_time_seconds:.2f}s")
            print(f"Snapshot actualizado:           {'Sí' if summary.snapshot_updated else 'No'}")

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


def snapshot_info():
    """Muestra información del snapshot actual"""
    print("\n" + "=" * 60)
    print("INFORMACIÓN DEL SNAPSHOT")
    print("=" * 60 + "\n")

    sync_service = SyncService()
    info = sync_service.snapshot_service.get_snapshot_info()

    if not info.get('exists'):
        print("❌ No existe snapshot previo.")
        print("   La primera sincronización será completa.")
        return 0

    if info.get('corrupted'):
        print("⚠️  Snapshot corrupto.")
        print("   La próxima sincronización será completa.")
        return 1

    if 'error' in info:
        print(f"❌ Error: {info['error']}")
        return 1

    print(f"✓ Última sincronización:  {info['last_sync']}")
    print(f"  Total de productos:     {info['total_products']}")
    print(f"  Tamaño del archivo:     {info['file_size_kb']} KB")
    print(f"  Ubicación:              {info['file_path']}")
    print()

    return 0


def preview_changes():
    """Muestra preview de cambios sin ejecutar sync"""
    print("\n" + "=" * 60)
    print("PREVIEW DE CAMBIOS (SIN EJECUTAR SYNC)")
    print("=" * 60 + "\n")

    try:
        sync_service = SyncService()

        # Leer inventario de Odoo
        stock_quants = sync_service.odoo_client.get_inventory_by_location(settings.ODOO_LOCATION_ID)

        if not stock_quants:
            print("❌ No se encontró inventario en Odoo.")
            return 1

        # Cargar snapshot y detectar cambios
        snapshot = sync_service.snapshot_service.load_snapshot()
        changes = sync_service.snapshot_service.compare_with_current(stock_quants, snapshot)

        print(f"Total productos en Odoo: {len(stock_quants)}")
        print()
        print("Cambios detectados:")
        print(f"  Nuevos:       {len(changes.new_products)}")
        print(f"  Modificados:  {len(changes.modified_products)}")
        print(f"  Eliminados:   {len(changes.deleted_skus)}")
        print(f"  Sin cambios:  {changes.unchanged_products}")
        print(f"  TOTAL:        {changes.total_changes}")
        print()

        if changes.total_changes == 0:
            print("✓ No hay cambios. La sincronización no hará llamadas a Shopify.")
            return 0

        # Calcular estimaciones
        products_to_sync = len(changes.new_products) + len(changes.modified_products) + len(changes.deleted_skus)
        estimated_batches = (products_to_sync // 250) + 1
        estimated_time = (products_to_sync * 0.2) + (estimated_batches * 1)
        estimated_api_calls = products_to_sync + estimated_batches

        print("Estimaciones:")
        print(f"  Productos a sincronizar: {products_to_sync}")
        print(f"  Batches:                 {estimated_batches}")
        print(f"  Tiempo estimado:         {estimated_time:.1f}s")
        print(f"  Llamadas API estimadas:  {estimated_api_calls}")
        print()

        # Ahorro vs sync completa
        full_sync_calls = len(stock_quants) + (len(stock_quants) // 250 + 1)
        saved_calls = full_sync_calls - estimated_api_calls
        saved_pct = (saved_calls / full_sync_calls * 100) if full_sync_calls > 0 else 0

        print(f"Ahorro vs sync completa:")
        print(f"  Llamadas ahorradas:      {saved_calls}")
        print(f"  Porcentaje de ahorro:    {saved_pct:.1f}%")
        print()

        return 0

    except Exception as e:
        print(f"❌ Error: {e}")
        return 1


def reset_snapshot():
    """Resetea el snapshot para forzar sync completa"""
    print("\n" + "=" * 60)
    print("RESETEAR SNAPSHOT")
    print("=" * 60 + "\n")

    print("⚠️  Esto eliminará el snapshot y forzará una sincronización completa.")

    sync_service = SyncService()
    success = sync_service.snapshot_service.reset_snapshot()

    if success:
        print("✓ Snapshot eliminado exitosamente.")
        print("  La próxima sincronización será completa.")
        return 0
    else:
        print("❌ Error al eliminar snapshot.")
        return 1


def main():
    """Punto de entrada del CLI"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Conector de stock Odoo-Shopify v2.1.0 (Optimizado)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  %(prog)s sync                    Sincronizar con detección de cambios (OPTIMIZADO)
  %(prog)s sync --verbose          Sincronizar con detalles
  %(prog)s sync --force            Forzar sync completa (ignorar snapshot)
  %(prog)s sync --single           Usar modo single (producto por producto)
  %(prog)s test                    Probar conexiones
  %(prog)s snapshot-info           Ver info del snapshot
  %(prog)s preview-changes         Preview de cambios sin ejecutar
  %(prog)s reset-snapshot          Resetear snapshot
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Comando a ejecutar')

    # Comando 'sync'
    sync_parser = subparsers.add_parser('sync', help='Sincronizar inventario (OPTIMIZADO)')
    sync_parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Mostrar detalles de cada producto'
    )
    sync_parser.add_argument(
        '--single',
        action='store_true',
        help='Usar modo single (producto por producto) en lugar de bulk'
    )
    sync_parser.add_argument(
        '--force',
        action='store_true',
        help='Forzar sincronización completa (ignorar snapshot)'
    )

    # Comando 'test'
    subparsers.add_parser('test', help='Probar conexiones con Odoo y Shopify')

    # Comando 'snapshot-info'
    subparsers.add_parser('snapshot-info', help='Ver información del snapshot')

    # Comando 'preview-changes'
    subparsers.add_parser('preview-changes', help='Preview de cambios sin ejecutar sync')

    # Comando 'reset-snapshot'
    subparsers.add_parser('reset-snapshot', help='Resetear snapshot (forzar sync completa)')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    if args.command == 'test':
        return test_connections()
    elif args.command == 'sync':
        use_bulk = not args.single
        return sync_inventory(verbose=args.verbose, bulk=use_bulk, force=args.force)
    elif args.command == 'snapshot-info':
        return snapshot_info()
    elif args.command == 'preview-changes':
        return preview_changes()
    elif args.command == 'reset-snapshot':
        return reset_snapshot()

    return 0


if __name__ == "__main__":
    sys.exit(main())
