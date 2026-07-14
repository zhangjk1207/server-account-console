from datetime import timedelta
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from app.services.backup import backup_sqlite_url, create_backup, remove_expired_backups, utc_now


def test_backup_removes_files_older_than_14_days(tmp_path) -> None:
    database = tmp_path / "source.db"
    with sqlite3.connect(database) as connection:
        connection.execute("create table checks (id integer primary key)")
    create_backup(database, tmp_path, now=utc_now())
    remove_expired_backups(tmp_path, now=utc_now() + timedelta(days=15))

    assert list(tmp_path.glob("backup-*.db")) == []


def test_backup_script_creates_a_sqlite_backup(tmp_path) -> None:
    database = tmp_path / "source.db"
    with sqlite3.connect(database) as connection:
        connection.execute("create table checks (id integer primary key)")
    backup_dir = tmp_path / "backups"
    script = Path(__file__).parents[3] / "scripts" / "backup.sh"

    result = subprocess.run(
        ["sh", str(script)],
        cwd=script.parents[1],
        env={**os.environ, "DATABASE_PATH": str(database), "BACKUP_DIR": str(backup_dir), "PYTHON": sys.executable},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert len(list(backup_dir.glob("backup-*.db"))) == 1


def test_backup_sqlite_url_creates_backup_beside_database(tmp_path) -> None:
    database = tmp_path / "app.db"
    with sqlite3.connect(database) as connection:
        connection.execute("create table checks (id integer primary key)")

    backup = backup_sqlite_url(f"sqlite:///{database}", now=utc_now())

    assert backup.parent == tmp_path / "backups"
    assert backup.exists()
