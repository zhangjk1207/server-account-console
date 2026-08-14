import os

import bcrypt
import pytest
from cryptography.fernet import Fernet

os.environ.setdefault("ADMIN_PASSWORD_HASH", bcrypt.hashpw(b"correct-horse", bcrypt.gensalt()).decode())
os.environ.setdefault("SESSION_SECRET", "test-session-secret-that-is-long-enough")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode())
os.environ.setdefault("AGENT_RUNTIME_TOKEN", "test-agent-runtime-token")


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
