from app.db.models import Host
from app.services.hosts import HostProbeResult, apply_probe_result


def test_changed_host_fingerprint_blocks_the_host() -> None:
    host = Host(name="lab-01", address="192.0.2.10", host_key_fingerprint="SHA256:old")

    apply_probe_result(host, HostProbeResult(fingerprint="SHA256:new", reachable=True, latency_ms=9))

    assert host.status == "fingerprint_changed"
