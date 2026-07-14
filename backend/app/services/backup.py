import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def create_backup(database: Path, backup_dir: Path, now: datetime) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    destination = backup_dir / f"backup-{now.strftime('%Y%m%d-%H%M%S')}.db"
    with sqlite3.connect(database) as source, sqlite3.connect(destination) as target:
        source.backup(target)
    return destination


def remove_expired_backups(backup_dir: Path, now: datetime, retention_days: int = 14) -> None:
    cutoff = now.timestamp() - retention_days * 86400
    for backup in backup_dir.glob("backup-*.db"):
        if backup.stat().st_mtime < cutoff:
            backup.unlink()
