import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def create_backup(database: Path, backup_dir: Path, now: datetime) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    destination = backup_dir / f"backup-{now.strftime('%Y%m%d-%H%M%S')}.db"
    with closing(sqlite3.connect(database)) as source, closing(sqlite3.connect(destination)) as target:
        with target:
            source.backup(target)
    return destination


def backup_sqlite_url(database_url: str, *, now: datetime | None = None) -> Path:
    if not database_url.startswith("sqlite:///"):
        raise ValueError("仅支持 SQLite 数据库备份")
    database = Path(database_url.removeprefix("sqlite:///"))
    backup_dir = database.parent / "backups"
    timestamp = now or utc_now()
    backup = create_backup(database, backup_dir, timestamp)
    remove_expired_backups(backup_dir, timestamp)
    return backup


def remove_expired_backups(backup_dir: Path, now: datetime, retention_days: int = 14) -> None:
    cutoff = now.timestamp() - retention_days * 86400
    for backup in backup_dir.glob("backup-*.db"):
        if backup.stat().st_mtime < cutoff:
            backup.unlink()
