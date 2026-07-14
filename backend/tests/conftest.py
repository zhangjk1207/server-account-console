import os
from pathlib import Path

import bcrypt
import pytest

os.environ.setdefault("ADMIN_PASSWORD_HASH", bcrypt.hashpw(b"correct-horse", bcrypt.gensalt()).decode())
os.environ.setdefault("SESSION_SECRET", "test-session-secret-that-is-long-enough")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
test_key = Path("/tmp/server-account-console-test-key")
test_key.write_text("test key", encoding="utf-8")
test_key.chmod(0o600)
os.environ.setdefault("CONTROL_SSH_KEY_PATH", str(test_key))


@pytest.fixture(autouse=True)
def reset_database():
    from app.db import models  # noqa: F401
    from app.db.base import Base
    from app.db.session import SessionLocal

    engine = SessionLocal.kw["bind"]
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
