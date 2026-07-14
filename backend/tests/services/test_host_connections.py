from cryptography.fernet import Fernet

from app.core.config import get_settings
from app.db.models import Host, HostCredential
from app.db.session import SessionLocal
from app.services import host_connections
from app.services.credentials import CredentialCipher


def make_credential(host: Host) -> HostCredential:
    cipher = CredentialCipher.from_settings()
    return HostCredential(
        host_id=host.id,
        private_key_ciphertext=cipher.encrypt("-----BEGIN OPENSSH PRIVATE KEY-----\nkey\n-----END OPENSSH PRIVATE KEY-----\n"),
        sudo_password_ciphertext=cipher.encrypt("sudo-secret"),
    )


def test_unconfirmed_host_returns_fingerprint_without_attempting_login(monkeypatch) -> None:
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode())
    get_settings.cache_clear()
    with SessionLocal() as session:
        host = Host(name="lab-01", address="192.0.2.10")
        session.add(host)
        session.flush()
        session.add(make_credential(host))
        session.commit()
        monkeypatch.setattr(host_connections, "scan_host_key", lambda _host: ("SHA256:new", "lab-01 ssh-ed25519 AAAA", None))
        monkeypatch.setattr(host_connections.subprocess, "run", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("不得尝试 SSH 登录")))

        result = host_connections.test_host_credential(session, host)

        assert result.requires_confirmation is True
        assert result.ssh_ok is None
        assert result.sudo_ok is None
    get_settings.cache_clear()


def test_confirmed_host_checks_ssh_then_forced_sudo(monkeypatch) -> None:
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode())
    get_settings.cache_clear()
    commands: list[list[str]] = []

    class Result:
        def __init__(self, returncode: int = 0) -> None:
            self.returncode = returncode
            self.stderr = ""

    def fake_run(command, **_kwargs):
        commands.append(command)
        return Result()

    with SessionLocal() as session:
        host = Host(name="lab-01", address="192.0.2.10", host_key_fingerprint="SHA256:known")
        session.add(host)
        session.flush()
        session.add(make_credential(host))
        session.commit()
        monkeypatch.setattr(host_connections, "scan_host_key", lambda _host: ("SHA256:known", "lab-01 ssh-ed25519 AAAA", None))
        monkeypatch.setattr(host_connections.subprocess, "run", fake_run)

        result = host_connections.test_host_credential(session, host)

        assert result.ssh_ok is True
        assert result.sudo_ok is True
        assert commands[0][-1] == "true"
        assert commands[1][-1] == "sudo -S -k -p '' true"
    get_settings.cache_clear()
