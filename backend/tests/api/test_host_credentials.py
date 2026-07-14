import asyncio

import httpx
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import select

from app.core.config import get_settings
from app.api import host_credentials as credential_api
from app.db.models import Host, HostCredential
from app.db.session import SessionLocal
from app.main import app
from app.services.host_connections import CredentialProbeResult


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


def test_confirming_a_fingerprint_uses_the_saved_host_credential(monkeypatch) -> None:
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode())
    get_settings.cache_clear()

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/api/auth/login", json={"password": "correct-horse"})
            token = (await client.get("/api/auth/csrf")).json()["token"]
            host = await client.post("/api/hosts", json={**HOST_PAYLOAD, "name": "confirm-host"}, headers={"X-CSRF-Token": token})
            host_id = host.json()["id"]
            await client.put(
                f"/api/hosts/{host_id}/credentials",
                headers={"X-CSRF-Token": token},
                data={"sudo_password": "sudo-secret"},
                files={"private_key_file": ("id_ed25519", private_key_file(), "application/octet-stream")},
            )
            monkeypatch.setattr(
                "app.api.hosts.test_host_credential",
                lambda _session, _host: __import__("app.services.host_connections", fromlist=["CredentialProbeResult"]).CredentialProbeResult(
                    fingerprint="SHA256:confirmed", requires_confirmation=False, ssh_ok=True, sudo_ok=True, error=None, latency_ms=7
                ),
            )
            monkeypatch.setattr("app.api.hosts._scan_ed25519_key", lambda _host: ("SHA256:confirmed", "confirm-host ssh-ed25519 AAAA", None))
            response = await client.post(
                f"/api/hosts/{host_id}/confirm-fingerprint",
                json={"fingerprint": "SHA256:confirmed"},
                headers={"X-CSRF-Token": token},
            )

            assert response.status_code == 200
            assert response.json()["status"] == "reachable"
            with SessionLocal() as session:
                credential = session.query(HostCredential).filter(HostCredential.host_id == host_id).one()
                assert credential.ssh_verified is True
                assert credential.sudo_verified is True

    try:
        asyncio.run(scenario())
    finally:
        get_settings.cache_clear()


def test_credential_test_reports_independent_ssh_and_sudo_results(monkeypatch) -> None:
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode())
    get_settings.cache_clear()

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/api/auth/login", json={"password": "correct-horse"})
            token = (await client.get("/api/auth/csrf")).json()["token"]
            host = await client.post("/api/hosts", json={**HOST_PAYLOAD, "name": "probe-host"}, headers={"X-CSRF-Token": token})
            host_id = host.json()["id"]
            await client.put(
                f"/api/hosts/{host_id}/credentials",
                headers={"X-CSRF-Token": token},
                data={"sudo_password": "sudo-secret"},
                files={"private_key_file": ("id_ed25519", private_key_file(), "application/octet-stream")},
            )
            monkeypatch.setattr(
                credential_api,
                "test_host_credential",
                lambda _session, _host: CredentialProbeResult(
                    fingerprint="SHA256:known", requires_confirmation=False, ssh_ok=True, sudo_ok=False, error="sudo 被拒绝", latency_ms=11
                ),
            )

            response = await client.post(f"/api/hosts/{host_id}/credentials/test", headers={"X-CSRF-Token": token})

            assert response.status_code == 200
            assert response.json() == {
                "fingerprint": "SHA256:known",
                "requires_confirmation": False,
                "ssh_ok": True,
                "sudo_ok": False,
                "error": "sudo 被拒绝",
                "latency_ms": 11,
            }
            with SessionLocal() as session:
                credential = session.query(HostCredential).filter(HostCredential.host_id == host_id).one()
                assert credential.ssh_verified is True
                assert credential.sudo_verified is False

    try:
        asyncio.run(scenario())
    finally:
        get_settings.cache_clear()
