import asyncio

import httpx
import pytest

from app.api import access_grants as access_grants_api
from app.db.models import Host, HostAccessGrant, HostCredential, ManagedUser, PermissionTemplate, SshPublicKey
from app.db.session import SessionLocal
from app.main import app


def test_provision_preview_uses_server_calculated_data_directory(monkeypatch: pytest.MonkeyPatch) -> None:
    with SessionLocal() as session:
        host = Host(name="gpu-01", address="192.0.2.10", data_root="/mnt/train", status="reachable", host_key_fingerprint="SHA256:known")
        user = ManagedUser(username="alice", display_name="Alice")
        template = PermissionTemplate(name="Docker", groups=["docker"])
        session.add_all([host, user, template])
        session.flush()
        session.add_all([
            SshPublicKey(managed_user_id=user.id, public_key="ssh-ed25519 AAAA alice", fingerprint="SHA256:alice", comment="alice"),
            HostCredential(host_id=host.id, private_key_ciphertext="cipher", sudo_password_ciphertext="cipher", ssh_verified=True, sudo_verified=True),
        ])
        session.commit()
        host_id, user_id, template_id = host.id, user.id, template.id

    def fake_start(session, user, rows, operation, *, check):
        return access_grants_api.create_access_grant_job(session, user, rows, operation=operation, check=check)

    monkeypatch.setattr(access_grants_api, "create_and_start_access_grant_job", fake_start)

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/api/auth/login", json={"password": "correct-horse"})
            token = (await client.get("/api/auth/csrf")).json()["token"]
            response = await client.post(
                f"/api/users/{user_id}/access-grants/preview",
                json={"grants": [{"host_id": host_id, "username": "alice-gpu", "permission_template_id": template_id}]},
                headers={"X-CSRF-Token": token},
            )
            assert response.status_code == 202
            row = response.json()["request_snapshot"]["grants"][0]
            assert row["data_directory"] == "/mnt/train/alice-gpu"
            assert row["groups"] == ["docker"]
            assert "data_directory" not in response.json()["user_snapshot"]

    asyncio.run(scenario())


def test_provision_preview_rejects_a_machine_without_data_root(monkeypatch: pytest.MonkeyPatch) -> None:
    with SessionLocal() as session:
        host = Host(name="gpu-01", address="192.0.2.10", status="reachable")
        user = ManagedUser(username="alice")
        session.add_all([host, user])
        session.flush()
        session.add(SshPublicKey(managed_user_id=user.id, public_key="ssh-ed25519 AAAA alice", fingerprint="SHA256:alice", comment="alice"))
        session.commit()
        host_id, user_id = host.id, user.id

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/api/auth/login", json={"password": "correct-horse"})
            token = (await client.get("/api/auth/csrf")).json()["token"]
            response = await client.post(
                f"/api/users/{user_id}/access-grants/preview",
                json={"grants": [{"host_id": host_id, "username": "alice"}]},
                headers={"X-CSRF-Token": token},
            )
            assert response.status_code == 422
            assert "数据根目录" in response.json()["detail"]

    asyncio.run(scenario())


def test_revoke_preview_keeps_data_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    with SessionLocal() as session:
        host = Host(name="gpu-01", address="192.0.2.10", data_root="/mnt/train", status="reachable", host_key_fingerprint="SHA256:known")
        user = ManagedUser(username="alice")
        session.add_all([host, user])
        session.flush()
        grant = HostAccessGrant(host_id=host.id, managed_user_id=user.id, username="alice", data_directory="/mnt/train/alice")
        session.add_all([
            grant,
            SshPublicKey(managed_user_id=user.id, public_key="ssh-ed25519 AAAA alice", fingerprint="SHA256:alice", comment="alice"),
            HostCredential(host_id=host.id, private_key_ciphertext="cipher", sudo_password_ciphertext="cipher", ssh_verified=True, sudo_verified=True),
        ])
        session.commit()
        user_id, grant_id, host_id = user.id, grant.id, host.id

    monkeypatch.setattr(
        access_grants_api,
        "create_and_start_access_grant_job",
        lambda session, user, rows, operation, *, check: access_grants_api.create_access_grant_job(session, user, rows, operation=operation, check=check),
    )

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/api/auth/login", json={"password": "correct-horse"})
            token = (await client.get("/api/auth/csrf")).json()["token"]
            response = await client.post(
                f"/api/users/{user_id}/access-grants/revoke/preview",
                json={"grants": [{"grant_id": grant_id}]},
                headers={"X-CSRF-Token": token},
            )
            assert response.status_code == 202
            row = response.json()["request_snapshot"]["grants"][0]
            assert row["grant_id"] == grant_id
            assert row["host_id"] == host_id
            assert row["username"] == "alice"
            assert row["data_root"] == "/mnt/train"
            assert row["data_directory"] == "/mnt/train/alice"
            assert row["delete_data"] is False
            assert row["command_preview"]["commands"]

    asyncio.run(scenario())


def test_revoke_preview_allows_a_disabled_member_without_enabled_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    with SessionLocal() as session:
        host = Host(name="gpu-revoke", address="192.0.2.12", data_root="/mnt/train", status="reachable", host_key_fingerprint="SHA256:known")
        user = ManagedUser(username="departed", enabled=False)
        session.add_all([host, user])
        session.flush()
        grant = HostAccessGrant(host_id=host.id, managed_user_id=user.id, username="departed", data_directory="/mnt/train/departed")
        session.add_all([grant, HostCredential(host_id=host.id, private_key_ciphertext="cipher", sudo_password_ciphertext="cipher", ssh_verified=True, sudo_verified=True)])
        session.commit()
        user_id, grant_id = user.id, grant.id

    monkeypatch.setattr(access_grants_api, "create_and_start_access_grant_job", lambda session, user, rows, operation, *, check: access_grants_api.create_access_grant_job(session, user, rows, operation=operation, check=check))

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/api/auth/login", json={"password": "correct-horse"})
            token = (await client.get("/api/auth/csrf")).json()["token"]
            response = await client.post(f"/api/users/{user_id}/access-grants/revoke/preview", json={"grants": [{"grant_id": grant_id}]}, headers={"X-CSRF-Token": token})
            assert response.status_code == 202

    asyncio.run(scenario())


def test_provision_preview_rejects_an_active_username_owned_by_another_member(monkeypatch: pytest.MonkeyPatch) -> None:
    with SessionLocal() as session:
        host = Host(name="gpu-collision", address="192.0.2.13", data_root="/mnt/train", status="reachable", host_key_fingerprint="SHA256:known")
        user = ManagedUser(username="alice")
        other = ManagedUser(username="bob")
        session.add_all([host, user, other])
        session.flush()
        session.add_all([
            HostAccessGrant(host_id=host.id, managed_user_id=other.id, username="shared", data_directory="/mnt/train/shared"),
            SshPublicKey(managed_user_id=user.id, public_key="ssh-ed25519 AAAA alice", fingerprint="SHA256:alice", comment="alice"),
            HostCredential(host_id=host.id, private_key_ciphertext="cipher", sudo_password_ciphertext="cipher", ssh_verified=True, sudo_verified=True),
        ])
        session.commit()
        user_id, host_id = user.id, host.id

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/api/auth/login", json={"password": "correct-horse"})
            token = (await client.get("/api/auth/csrf")).json()["token"]
            response = await client.post(f"/api/users/{user_id}/access-grants/preview", json={"grants": [{"host_id": host_id, "username": "shared"}]}, headers={"X-CSRF-Token": token})
            assert response.status_code == 422
            assert "用户名" in response.json()["detail"]

    asyncio.run(scenario())


def test_adopted_account_preview_does_not_require_data_root_and_freezes_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    with SessionLocal() as session:
        host = Host(name="gpu-existing", address="192.0.2.20", status="reachable", host_key_fingerprint="SHA256:known")
        user = ManagedUser(username="alice")
        session.add_all([host, user])
        session.flush()
        session.add_all([
            SshPublicKey(managed_user_id=user.id, public_key="ssh-ed25519 AAAA alice", fingerprint="SHA256:alice", comment="alice"),
            HostCredential(host_id=host.id, private_key_ciphertext="cipher", sudo_password_ciphertext="cipher", ssh_verified=True, sudo_verified=True),
        ])
        session.commit()
        host_id, user_id = host.id, user.id

    monkeypatch.setattr(
        access_grants_api,
        "create_and_start_access_grant_job",
        lambda session, user, rows, operation, *, check: access_grants_api.create_access_grant_job(session, user, rows, operation=operation, check=check),
    )

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/api/auth/login", json={"password": "correct-horse"})
            token = (await client.get("/api/auth/csrf")).json()["token"]
            response = await client.post(
                f"/api/users/{user_id}/access-grants/preview",
                json={
                    "grants": [{
                        "host_id": host_id,
                        "username": "legacy-alice",
                        "account_origin": "adopted",
                        "existing_account": {"uid": 1007, "primary_group": "research", "home": "/srv/homes/legacy-alice"},
                    }]
                },
                headers={"X-CSRF-Token": token},
            )

            assert response.status_code == 202
            row = response.json()["request_snapshot"]["grants"][0]
            assert row["account_origin"] == "adopted"
            assert row["remote_uid"] == 1007
            assert row["remote_primary_group"] == "research"
            assert row["remote_home"] == "/srv/homes/legacy-alice"
            assert row["data_directory"] is None
            assert any("usermod -U legacy-alice" in command for command in row["command_preview"]["commands"])
            assert row["command_preview"]["key_fingerprints"] == ["SHA256:alice"]

    asyncio.run(scenario())


def test_adopted_account_preview_requires_observed_identity() -> None:
    with SessionLocal() as session:
        host = Host(name="gpu-missing-observation", address="192.0.2.22", status="reachable", host_key_fingerprint="SHA256:known")
        user = ManagedUser(username="alice")
        session.add_all([host, user])
        session.flush()
        session.add_all([
            SshPublicKey(managed_user_id=user.id, public_key="ssh-ed25519 AAAA alice", fingerprint="SHA256:alice", comment="alice"),
            HostCredential(host_id=host.id, private_key_ciphertext="cipher", sudo_password_ciphertext="cipher", ssh_verified=True, sudo_verified=True),
        ])
        session.commit()
        host_id, user_id = host.id, user.id

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/api/auth/login", json={"password": "correct-horse"})
            token = (await client.get("/api/auth/csrf")).json()["token"]
            response = await client.post(
                f"/api/users/{user_id}/access-grants/preview",
                json={"grants": [{"host_id": host_id, "username": "alice", "account_origin": "adopted"}]},
                headers={"X-CSRF-Token": token},
            )

            assert response.status_code == 422
            assert "existing_account" in response.text

    asyncio.run(scenario())


def test_access_grant_list_exposes_adopted_account_metadata() -> None:
    with SessionLocal() as session:
        host = Host(name="gpu-adopted-list", address="192.0.2.21")
        user = ManagedUser(username="alice")
        session.add_all([host, user])
        session.flush()
        session.add(HostAccessGrant(
            host_id=host.id,
            managed_user_id=user.id,
            username="legacy-alice",
            account_origin="adopted",
            remote_uid=1007,
            remote_primary_group="research",
            remote_home="/srv/homes/legacy-alice",
            managed_public_keys=["ssh-ed25519 AAAA alice"],
            managed_key_fingerprints=["SHA256:alice"],
            data_directory=None,
        ))
        session.commit()
        user_id = user.id

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/api/auth/login", json={"password": "correct-horse"})
            response = await client.get(f"/api/users/{user_id}/access-grants")

            assert response.status_code == 200
            grant = response.json()[0]
            assert grant["account_origin"] == "adopted"
            assert grant["remote_uid"] == 1007
            assert grant["remote_home"] == "/srv/homes/legacy-alice"
            assert grant["data_directory"] is None
            assert grant["managed_key_fingerprints"] == ["SHA256:alice"]

    asyncio.run(scenario())
