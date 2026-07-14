#!/usr/bin/env sh
set -eu

DATABASE_PATH=${DATABASE_PATH:-./runtime/app.db}
BACKUP_DIR=${BACKUP_DIR:-./runtime/backups}
PYTHON=${PYTHON:-python3}
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

export DATABASE_PATH BACKUP_DIR
PYTHONPATH="$SCRIPT_DIR/../backend${PYTHONPATH:+:$PYTHONPATH}" "$PYTHON" - <<'PY'
import os
from pathlib import Path

from app.services.backup import create_backup, remove_expired_backups, utc_now

now = utc_now()
create_backup(Path(os.environ["DATABASE_PATH"]), Path(os.environ["BACKUP_DIR"]), now)
remove_expired_backups(Path(os.environ["BACKUP_DIR"]), now)
PY
