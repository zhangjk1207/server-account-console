import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Host
from app.schemas.host import HostCreate, HostUpdate


@dataclass(frozen=True)
class HostProbeResult:
    fingerprint: str | None
    reachable: bool
    latency_ms: int | None = None
    error: str | None = None
    known_host_line: str | None = None


def normalize_tags(tags: list[str]) -> list[str]:
    return sorted({tag.strip().lower() for tag in tags if tag.strip()})


def create_host(session: Session, payload: HostCreate) -> Host:
    host = Host(
        name=payload.name,
        address=payload.address,
        port=payload.port,
        ssh_user=payload.ssh_user,
        tags=normalize_tags(payload.tags),
        data_root=payload.data_root,
    )
    session.add(host)
    session.commit()
    session.refresh(host)
    return host


def update_host(session: Session, host: Host, payload: HostUpdate) -> Host:
    changes = payload.model_dump(exclude_unset=True)
    if "tags" in changes:
        changes["tags"] = normalize_tags(changes["tags"])
    if {"address", "port", "ssh_user"}.intersection(changes):
        host.host_key_fingerprint = None
        host.status = "unconfirmed"
    for field, value in changes.items():
        setattr(host, field, value)
    session.commit()
    session.refresh(host)
    return host


def get_active_host(session: Session, host_id: str) -> Host | None:
    return session.scalar(select(Host).where(Host.id == host_id, Host.archived.is_(False)))


def apply_probe_result(host: Host, result: HostProbeResult) -> None:
    host.last_probe_at = datetime.now(timezone.utc)
    host.last_probe_latency_ms = result.latency_ms
    host.last_probe_error = result.error
    if host.host_key_fingerprint and result.fingerprint and host.host_key_fingerprint != result.fingerprint:
        host.status = "fingerprint_changed"
    elif not host.host_key_fingerprint:
        host.status = "unconfirmed"
    elif result.reachable:
        host.status = "reachable"
    else:
        host.status = "unreachable"


def _ssh_keyscan_candidates() -> list[str]:
    candidates: list[str] = []
    if configured := os.environ.get("SSH_KEYSCAN_BINARY"):
        candidates.append(configured)
    if os.name == "nt":
        program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
        candidates.append(str(Path(program_files) / "Git" / "usr" / "bin" / "ssh-keyscan.exe"))
    if discovered := shutil.which("ssh-keyscan"):
        candidates.append(discovered)
    candidates.append("ssh-keyscan")
    return list(dict.fromkeys(candidates))


def _scan_ed25519_key(host: Host) -> tuple[str | None, str | None, str | None]:
    line = None
    errors: list[str] = []
    for binary in _ssh_keyscan_candidates():
        try:
            scan = subprocess.run(
                [binary, "-T", "5", "-p", str(host.port), "-t", "ed25519", host.address],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (FileNotFoundError, OSError) as error:
            errors.append(str(error))
            continue
        line = next((entry for entry in scan.stdout.splitlines() if entry and not entry.startswith("#")), None)
        if line:
            break
        if scan.stderr.strip():
            errors.append(scan.stderr.strip())
    if not line:
        return None, None, (errors[-1] if errors else "No ED25519 host key was returned")

    fingerprint = subprocess.run(
        ["ssh-keygen", "-lf", "-", "-E", "sha256"],
        input=f"{line}\n",
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if fingerprint.returncode != 0:
        return None, None, (fingerprint.stderr.strip() or "无法计算主机密钥指纹")
    parts = fingerprint.stdout.split()
    value = next((part for part in parts if part.startswith("SHA256:")), None)
    return value, line, None


def probe_host(host: Host) -> HostProbeResult:
    started = time.monotonic()
    fingerprint, known_host_line, scan_error = _scan_ed25519_key(host)
    if scan_error:
        return HostProbeResult(fingerprint=None, reachable=False, error=scan_error)
    if not host.host_key_fingerprint or host.host_key_fingerprint != fingerprint:
        return HostProbeResult(fingerprint=fingerprint, reachable=False, known_host_line=known_host_line)
    latency_ms = round((time.monotonic() - started) * 1000)
    return HostProbeResult(
        fingerprint=fingerprint,
        reachable=False,
        latency_ms=latency_ms,
        error="请先配置并验证主机连接凭证",
        known_host_line=known_host_line,
    )
