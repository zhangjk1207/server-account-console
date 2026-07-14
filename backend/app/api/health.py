import importlib.util
from pathlib import Path

from fastapi import APIRouter, Response, status
from sqlalchemy import create_engine, text

from app.core.config import get_settings
from app.services.credentials import CredentialCipher, CredentialConfigurationError

router = APIRouter()


@router.get("/health")
def health(response: Response) -> dict[str, object]:
    settings = get_settings()
    checks = {
        "database": "degraded",
        "ansible": "degraded",
        "credential_encryption": "degraded",
    }

    try:
        engine = create_engine(settings.database_url)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        pass

    project_dir = Path(__file__).resolve().parents[2] / "ansible"
    if project_dir.is_dir() and importlib.util.find_spec("ansible_runner"):
        checks["ansible"] = "ok"

    try:
        CredentialCipher.from_settings()
        checks["credential_encryption"] = "ok"
    except CredentialConfigurationError:
        pass

    if any(value != "ok" for value in checks.values()):
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "degraded", "checks": checks}
    return {"status": "ok", "checks": checks}
