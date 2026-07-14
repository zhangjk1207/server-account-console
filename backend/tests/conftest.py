import os

import bcrypt

os.environ.setdefault("ADMIN_PASSWORD_HASH", bcrypt.hashpw(b"correct-horse", bcrypt.gensalt()).decode())
os.environ.setdefault("SESSION_SECRET", "test-session-secret-that-is-long-enough")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
