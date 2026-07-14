import asyncio

import httpx
from cryptography.fernet import Fernet

from app.core.config import get_settings
from app.api import host_operations as operations_api
from app.db.models import Job
from app.db.session import SessionLocal
from app.main import app
from app.schemas.host_operation import HostUserRead


def test_host_operation_preview_rejects_host_without_verified_sudo(monkeypatch) -> None:
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode())
    get_settings.cache_clear()

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/api/auth/login", json={"password": "correct-horse"})
            token = (await client.get("/api/auth/csrf")).json()["token"]
            host = await client.post(
                "/api/hosts",
                json={"name": "no-sudo", "address": "192.0.2.10", "port": 22, "ssh_user": "ops", "tags": []},
                headers={"X-CSRF-Token": token},
            )
            response = await client.post(
                f"/api/hosts/{host.json()['id']}/user-operations/preview",
                json={"action": "lock", "username": "alice"},
                headers={"X-CSRF-Token": token},
            )

            assert response.status_code == 422
            assert response.json()["detail"] == "连接凭证尚未通过 SSH 和 sudo 验证"

    try:
        asyncio.run(scenario())
    finally:
        get_settings.cache_clear()


def test_host_users_endpoint_returns_fixed_inventory(monkeypatch) -> None:
    async def scenario() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/api/auth/login", json={"password": "correct-horse"})
            token = (await client.get("/api/auth/csrf")).json()["token"]
            host = await client.post(
                "/api/hosts",
                json={"name": "inventory-host", "address": "192.0.2.10", "port": 22, "ssh_user": "ops", "tags": []},
                headers={"X-CSRF-Token": token},
            )
            monkeypatch.setattr(
                operations_api,
                "list_host_users",
                lambda _session, _host: [
                    HostUserRead(username="alice", uid=1001, primary_group="1001", groups=[], shell="/bin/bash", home="/home/alice", locked=None, expires_at=None)
                ],
            )

            response = await client.get(f"/api/hosts/{host.json()['id']}/users")

            assert response.status_code == 200
            assert response.json()[0]["username"] == "alice"

    asyncio.run(scenario())


def test_host_user_keys_endpoint_returns_public_key_metadata(monkeypatch) -> None:
    async def scenario() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/api/auth/login", json={"password": "correct-horse"})
            token = (await client.get("/api/auth/csrf")).json()["token"]
            host = await client.post(
                "/api/hosts",
                json={"name": "key-host", "address": "192.0.2.10", "port": 22, "ssh_user": "ops", "tags": []},
                headers={"X-CSRF-Token": token},
            )
            monkeypatch.setattr(
                operations_api,
                "list_host_user_keys",
                lambda _session, _host, _username: [{"public_key": "ssh-ed25519 AAAA", "fingerprint": "SHA256:key", "comment": "alice@laptop"}],
            )

            response = await client.get(f"/api/hosts/{host.json()['id']}/users/alice/keys")

            assert response.status_code == 200
            assert response.json() == [{"public_key": "ssh-ed25519 AAAA", "fingerprint": "SHA256:key", "comment": "alice@laptop"}]

    asyncio.run(scenario())


def test_password_reset_execution_requires_one_time_password() -> None:
    with SessionLocal() as session:
        job = Job(
            kind="host_user_operation",
            state="ready_to_confirm",
            request_snapshot={"operation": {"action": "reset_password", "username": "alice"}},
        )
        session.add(job)
        session.commit()
        job_id = job.id

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/api/auth/login", json={"password": "correct-horse"})
            token = (await client.get("/api/auth/csrf")).json()["token"]
            response = await client.post(f"/api/host-operations/{job_id}/execute", json={}, headers={"X-CSRF-Token": token})

            assert response.status_code == 422
            assert response.json()["detail"] == "重置密码需要输入新密码"

    asyncio.run(scenario())


def test_sshd_password_login_preview_rejects_unverified_host() -> None:
    async def scenario() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/api/auth/login", json={"password": "correct-horse"})
            token = (await client.get("/api/auth/csrf")).json()["token"]
            host = await client.post(
                "/api/hosts",
                json={"name": "sshd-host", "address": "192.0.2.10", "port": 22, "ssh_user": "ops", "tags": []},
                headers={"X-CSRF-Token": token},
            )

            response = await client.post(
                f"/api/hosts/{host.json()['id']}/ssh-password-authentication/preview",
                json={"enabled": False},
                headers={"X-CSRF-Token": token},
            )

            assert response.status_code == 422
            assert response.json()["detail"] == "连接凭证尚未通过 SSH 和 sudo 验证"

    asyncio.run(scenario())
