from app.db.models import Host
from app.services import hosts
from app.services.hosts import HostProbeResult, apply_probe_result


def test_changed_host_fingerprint_blocks_the_host() -> None:
    host = Host(name="lab-01", address="192.0.2.10", host_key_fingerprint="SHA256:old")

    apply_probe_result(host, HostProbeResult(fingerprint="SHA256:new", reachable=True, latency_ms=9))

    assert host.status == "fingerprint_changed"


def test_host_key_scan_falls_back_when_first_binary_rejects_server_kex(monkeypatch) -> None:
    commands: list[str] = []

    class Result:
        def __init__(self, stdout: str = "", stderr: str = "", returncode: int = 0) -> None:
            self.stdout = stdout
            self.stderr = stderr
            self.returncode = returncode

    def fake_run(command, **_kwargs):
        commands.append(command[0])
        if command[0] == "broken-keyscan":
            return Result(stderr="unsupported KEX", returncode=1)
        if command[0] == "working-keyscan":
            return Result(stdout="lab-01 ssh-ed25519 AAAA")
        return Result(stdout="256 SHA256:known lab-01 (ED25519)")

    monkeypatch.setattr(hosts, "_ssh_keyscan_candidates", lambda: ["broken-keyscan", "working-keyscan"])
    monkeypatch.setattr(hosts.subprocess, "run", fake_run)

    fingerprint, line, error = hosts._scan_ed25519_key(Host(name="lab-01", address="192.0.2.10"))

    assert error is None
    assert fingerprint == "SHA256:known"
    assert line == "lab-01 ssh-ed25519 AAAA"
    assert commands[:2] == ["broken-keyscan", "working-keyscan"]
