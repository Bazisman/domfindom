import shutil
import sqlite3
from pathlib import Path
from datetime import datetime
from utils.logger import app_logger

class DatabaseBackup:
    """Управление бэкапами базы данных"""
    
    def __init__(self, db_path: str = "finance.db", backup_dir: str = "backups"):
        self.db_path = Path(db_path)
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(exist_ok=True)
        
        # Храним последние 10 бэкапов
        self.max_backups = 10
    
    def create_backup(self, reason: str = "manual") -> Path:
        """Создать бэкап базы данных"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"finance_{timestamp}_{reason}.db"
        backup_path = self.backup_dir / backup_name
        
        try:
            # Создаем копию через sqlite3 для целостности
            conn = sqlite3.connect(self.db_path)
            backup_conn = sqlite3.connect(backup_path)
            conn.backup(backup_conn)
            backup_conn.close()
            conn.close()
            
            app_logger.info("Бэкап создан: %s", backup_path)
            self._cleanup_old_backups()
            return backup_path
            
        except Exception as e:
            app_logger.error("Ошибка создания бэкапа: %s", e)
            raise
    
    def _cleanup_old_backups(self):
        """Оставить только последние N бэкапов"""
        backups = sorted(self.backup_dir.glob("finance_*.db"))
        if len(backups) > self.max_backups:
            for old in backups[:-self.max_backups]:
                old.unlink()
                app_logger.debug("Удален старый бэкап: %s", old)