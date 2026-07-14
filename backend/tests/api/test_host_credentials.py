import asyncio

import httpx
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import HostCredential
from app.db.session import SessionLocal
from app.main import app


HOST_PAYLOAD = {
    "name": "credential-host",
    "address": "192.0.2.33",
    "port": 22,
    "ssh_user": "ops",
    "tags": [],
}


def private_key_file() -> bytes:
    return Ed25519PrivateKey.generate().private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.OpenSSH,
        encryption_algorithm=serialization.NoEncryption(),
    )


def test_uploading_credential_returns_only_status_and_encrypts_secrets(monkeypatch) -> None:
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode())
    get_settings.cache_clear()

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/api/auth/login", json={"password": "correct-horse"})
            token = (await client.get("/api/auth/csrf")).json()["token"]
            host = await client.post("/api/hosts", json=HOST_PAYLOAD, headers={"X-CSRF-Token": token})
            response = await client.put(
                f"/api/hosts/{host.json()['id']}/credentials",
                headers={"X-CSRF-Token": token},
                data={"sudo_password": "sudo-secret"},
                files={"private_key_file": ("id_ed25519", private_key_file(), "application/octet-stream")},
            )

            assert response.status_code == 200
            assert response.json()["private_key_configured"] is True
            assert response.json()["sudo_password_configured"] is True
            assert "sudo-secret" not in response.text
            with SessionLocal() as session:
                record = session.scalar(select(HostCredential).where(HostCredential.host_id == host.json()["id"]))
                assert record is not None
                assert "sudo-secret" not in record.sudo_password_ciphertext

    try:
        asyncio.run(scenario())
    finally:
        get_settings.cache_clear()
