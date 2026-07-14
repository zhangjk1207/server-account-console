from sqlalchemy import select

from app.db.models import Host
from app.services.hosts import HostProbeResult
from app.services.probes import probe_all_hosts


def test_probe_all_hosts_skips_when_a_job_is_running() -> None:
    called = False

    def probe(_: Host) -> HostProbeResult:
        nonlocal called
        called = True
        return HostProbeResult(fingerprint="SHA256:test", reachable=True)

    result = probe_all_hosts(lambda: None, is_job_running=lambda: True, probe=probe)

    assert result == 0
    assert called is False


def test_probe_all_hosts_persists_confirmed_host_status() -> None:
    from app.db.session import SessionLocal

    with SessionLocal() as session:
        session.add(Host(name="lab-01", address="192.0.2.10", host_key_fingerprint="SHA256:test"))
        session.commit()

    def probe(_: Host) -> HostProbeResult:
        return HostProbeResult(fingerprint="SHA256:test", reachable=True, latency_ms=7)

    result = probe_all_hosts(SessionLocal, is_job_running=lambda: False, probe=probe)

    with SessionLocal() as session:
        host = session.scalar(select(Host).where(Host.name == "lab-01"))
        assert result == 1
        assert host is not None
        assert host.status == "reachable"
        assert host.last_probe_latency_ms == 7
