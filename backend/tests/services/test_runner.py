from pathlib import Path

from app.services.runner import redact_event


def test_redacts_private_key_path_and_material() -> None:
    event = {"stdout": "identity /run/secrets/control_ssh_key\n-----BEGIN OPENSSH PRIVATE KEY-----\nsecret"}

    redacted = redact_event(event, Path("/run/secrets/control_ssh_key"))

    assert "/run/secrets/control_ssh_key" not in redacted["stdout"]
    assert "OPENSSH PRIVATE KEY" not in redacted["stdout"]
