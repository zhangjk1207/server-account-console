from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def create_session_factory() -> sessionmaker[Session]:
    engine = create_engine(get_settings().database_url, connect_args={"check_same_thread": False})
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


SessionLocal = create_session_factory()


def get_db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
