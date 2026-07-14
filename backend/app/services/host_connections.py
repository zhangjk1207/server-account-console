import os
import subprocess
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from sqlalchemy.orm import Session

from app.db.models import Host, HostCredential
from app.services.credentials import CredentialCipher
from app.services.hosts import _scan_ed25519_key


@dataclass(frozen=True)
class CredentialProbeResult:
    fingerprint: str | None
    requires_confirmation: bool
    ssh_ok: bool | None
    sudo_ok: bool | None
    error: str | None
    latency_ms: int | None


@dataclass(frozen=True)
class DecryptedHostCredential:
    private_key: str
    sudo_password: str


def scan_host_key(host: Host) -> tuple[str | None, str | None, str | None]:
    return _scan_ed25519_key(host)


def get_host_credential(session: Session, host: Host) -> HostCredential:
    credential = session.query(HostCredential).filter(HostCredential.host_id == host.id).one_or_none()
    if credential is None:
        raise ValueError("机器尚未配置连接凭证")
    return credential


def decrypt_host_credential(session: Session, host: Host) -> DecryptedHostCredential:
    credential = get_host_credential(session, host)
    cipher = CredentialCipher.from_settings()
    return DecryptedHostCredential(
        private_key=cipher.decrypt(credential.private_key_ciphertext),
        sudo_password=cipher.decrypt(credential.sudo_password_ciphertext),
    )


@contextmanager
def private_key_file(private_key: str, directory: Path | None = None) -> Iterator[Path]:
    fd, filename = tempfile.mkstemp(prefix="host-key-", dir=directory)
    path = Path(filename)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(private_key)
        yield path
    finally:
        path.unlink(missing_ok=True)


@contextmanager
def known_hosts_file(line: str) -> Iterator[Path]:
    fd, filename = tempfile.mkstemp(prefix="known-hosts-")
    path = Path(filename)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(f"{line}\n")
        yield path
    finally:
        path.unlink(missing_ok=True)


def _strict_ssh_command(host: Host, key_path: Path, known_hosts: Path, remote_command: str) -> list[str]:
    return [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        f"UserKnownHostsFile={known_hosts}",
        "-o",
        "ConnectTimeout=5",
        "-i",
        str(key_path),
        "-p",
        str(host.port),
        f"{host.ssh_user}@{host.address}",
        remote_command,
    ]


def _error_summary(message: str, secret: str) -> str:
    return message.replace(secret, "[REDACTED]").replace("\n", " ").strip()[:1000]


def test_host_credential(session: Session, host: Host) -> CredentialProbeResult:
    started = time.monotonic()
    credential = decrypt_host_credential(session, host)
    fingerprint, known_line, scan_error = scan_host_key(host)
    if scan_error or fingerprint is None or known_line is None:
        return CredentialProbeResult(None, False, False, None, scan_error or "未获取到 ED25519 主机密钥", None)
    if host.host_key_fingerprint != fingerprint:
        return CredentialProbeResult(fingerprint, True, None, None, None, None)

    with private_key_file(credential.private_key) as key_path, known_hosts_file(known_line) as known_hosts:
        ssh = subprocess.run(
            _strict_ssh_command(host, key_path, known_hosts, "true"),
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        latency_ms = round((time.monotonic() - started) * 1000)
        if ssh.returncode != 0:
            return CredentialProbeResult(
                fingerprint,
                False,
                False,
                None,
                _error_summary(ssh.stderr or "SSH 登录失败", credential.sudo_password),
                latency_ms,
            )
        sudo = subprocess.run(
            _strict_ssh_command(host, key_path, known_hosts, "sudo -S -k -p '' true"),
            input=f"{credential.sudo_password}\n",
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    return CredentialProbeResult(
        fingerprint,
        False,
        True,
        sudo.returncode == 0,
        None if sudo.returncode == 0 else _error_summary(sudo.stderr or "sudo 验证失败", credential.sudo_password),
        round((time.monotonic() - started) * 1000),
    )


def apply_credential_probe(session: Session, host: Host, result: CredentialProbeResult) -> None:
    credential = get_host_credential(session, host)
    now = datetime.now(timezone.utc)
    credential.verified_at = now
    credential.ssh_verified = result.ssh_ok
    credential.sudo_verified = result.sudo_ok
    credential.last_error = result.error
    host.last_probe_at = now
    host.last_probe_latency_ms = result.latency_ms
    host.last_probe_error = result.error
    if result.requires_confirmation:
        host.status = "fingerprint_changed" if host.host_key_fingerprint else "unconfirmed"
    elif result.ssh_ok:
        host.status = "reachable"
    else:
        host.status = "unreachable"
