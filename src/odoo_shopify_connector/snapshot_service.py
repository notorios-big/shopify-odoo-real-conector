"""
Servicio para gestionar snapshots de sincronización.
"""
import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from .models import SyncSnapshot, SnapshotProduct, OdooStockQuant, ChangeDetectionResult
from .config import settings

logger = logging.getLogger(__name__)


class SnapshotService:
    """Servicio para gestionar snapshots de sincronización"""

    MAX_BACKUPS = 3

    def __init__(self):
        """Inicializa el servicio de snapshots"""
        # Usar configuración para el directorio de snapshots
        snapshot_dir = Path(settings.SNAPSHOT_DIR)
        self.SNAPSHOT_PATH = snapshot_dir / "last_sync_snapshot.json"
        self.BACKUP_PATH = snapshot_dir / "last_sync_snapshot.json.backup"

        # Crear directorio si no existe
        self.SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)

    def load_snapshot(self) -> Optional[SyncSnapshot]:
        """Carga el snapshot de la última sincronización"""
        if not self.SNAPSHOT_PATH.exists():
            logger.info("No existe snapshot previo. Primera sincronización.")
            return None

        try:
            with open(self.SNAPSHOT_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Convertir timestamps a datetime
            data['last_sync_timestamp'] = datetime.fromisoformat(data['last_sync_timestamp'])
            for sku, prod in data['products'].items():
                prod['last_updated'] = datetime.fromisoformat(prod['last_updated'])

            snapshot = SyncSnapshot(**data)
            logger.info(f"Snapshot cargado: {snapshot.total_products} productos, última sync: {snapshot.last_sync_timestamp}")
            return snapshot

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error(f"Snapshot corrupto: {e}. Se procederá con sync completa.")
            return None

    def save_snapshot(self, products: list[OdooStockQuant]) -> bool:
        """Guarda el snapshot actual con timestamp"""
        try:
            self.create_backup()

            now = datetime.now()
            snapshot_products = {
                p.sku: SnapshotProduct(
                    sku=p.sku,
                    quantity=int(p.quantity),
                    product_name=p.product_name,
                    product_id=p.product_id,
                    last_updated=now
                ) for p in products
            }

            snapshot = SyncSnapshot(
                last_sync_timestamp=now,
                total_products=len(products),
                products=snapshot_products
            )

            # Serializar a JSON
            data = snapshot.model_dump()
            data['last_sync_timestamp'] = data['last_sync_timestamp'].isoformat()
            for prod in data['products'].values():
                prod['last_updated'] = prod['last_updated'].isoformat()

            with open(self.SNAPSHOT_PATH, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            # Permisos restrictivos
            self.SNAPSHOT_PATH.chmod(0o600)

            logger.info(f"Snapshot guardado: {len(products)} productos")
            return True

        except Exception as e:
            logger.error(f"Error al guardar snapshot: {e}")
            return False

    def create_backup(self) -> bool:
        """Crea backup del snapshot antes de actualizar"""
        if not self.SNAPSHOT_PATH.exists():
            return True

        try:
            # Backup con timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_with_ts = Path(f"{self.BACKUP_PATH}.{timestamp}")
            shutil.copy2(self.SNAPSHOT_PATH, backup_with_ts)

            # Rotar backups antiguos (mantener solo últimos 3)
            backups = sorted(self.SNAPSHOT_PATH.parent.glob(f"{self.BACKUP_PATH.name}.*"))
            if len(backups) > self.MAX_BACKUPS:
                for old_backup in backups[:-self.MAX_BACKUPS]:
                    old_backup.unlink()
                    logger.debug(f"Backup antiguo eliminado: {old_backup}")

            logger.debug(f"Backup creado: {backup_with_ts}")
            return True

        except Exception as e:
            logger.warning(f"Error al crear backup: {e}")
            return False

    def compare_with_current(
        self,
        current_products: list[OdooStockQuant],
        snapshot: Optional[SyncSnapshot]
    ) -> ChangeDetectionResult:
        """Compara inventario actual con snapshot"""

        if not snapshot:
            # Primera sincronización: todos son nuevos
            return ChangeDetectionResult(
                new_products=current_products,
                modified_products=[],
                deleted_skus=[],
                unchanged_products=0,
                total_changes=len(current_products)
            )

        current_map = {p.sku: p for p in current_products}
        snapshot_map = snapshot.products

        new_products = []
        modified_products = []
        unchanged = 0

        # Detectar nuevos y modificados
        for sku, current in current_map.items():
            if sku not in snapshot_map:
                new_products.append(current)
            elif int(current.quantity) != snapshot_map[sku].quantity:
                modified_products.append(current)
            else:
                unchanged += 1

        # Detectar eliminados
        deleted_skus = [sku for sku in snapshot_map.keys() if sku not in current_map]

        total_changes = len(new_products) + len(modified_products) + len(deleted_skus)

        logger.info(
            f"Cambios detectados: {len(new_products)} nuevos, {len(modified_products)} modificados, "
            f"{len(deleted_skus)} eliminados, {unchanged} sin cambios"
        )

        return ChangeDetectionResult(
            new_products=new_products,
            modified_products=modified_products,
            deleted_skus=deleted_skus,
            unchanged_products=unchanged,
            total_changes=total_changes
        )

    def reset_snapshot(self) -> bool:
        """Elimina el snapshot para forzar sincronización completa"""
        try:
            if self.SNAPSHOT_PATH.exists():
                self.create_backup()
                self.SNAPSHOT_PATH.unlink()
                logger.info("Snapshot eliminado. Próxima sync será completa.")
            return True
        except Exception as e:
            logger.error(f"Error al eliminar snapshot: {e}")
            return False

    def get_snapshot_info(self) -> dict:
        """Obtiene información del snapshot actual"""
        if not self.SNAPSHOT_PATH.exists():
            return {
                "exists": False,
                "message": "No existe snapshot previo"
            }

        try:
            stat = self.SNAPSHOT_PATH.stat()
            snapshot = self.load_snapshot()

            if not snapshot:
                return {
                    "exists": True,
                    "corrupted": True,
                    "message": "Snapshot corrupto"
                }

            return {
                "exists": True,
                "last_sync": snapshot.last_sync_timestamp.isoformat(),
                "total_products": snapshot.total_products,
                "file_size_kb": round(stat.st_size / 1024, 2),
                "file_path": str(self.SNAPSHOT_PATH)
            }
        except Exception as e:
            return {
                "exists": True,
                "error": str(e)
            }
