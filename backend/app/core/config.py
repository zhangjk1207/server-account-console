from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    admin_password_hash: str
    session_secret: str
    database_url: str = "sqlite:////var/lib/server-account-console/app.db"
    app_origin: str = "http://127.0.0.1:5174"
    control_ssh_key_path: str = "/run/secrets/control_ssh_key"
    credential_encryption_key: str | None = None
    host_probe_interval_seconds: int = 300
    backup_interval_seconds: int = 86400

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
