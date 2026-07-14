from pathlib import Path
import json

from app.services.runner import redact_event


def test_redacts_private_key_path_and_material() -> None:
    event = {"stdout": "identity /run/secrets/control_ssh_key\n-----BEGIN OPENSSH PRIVATE KEY-----\nsecret"}

    redacted = redact_event(event, Path("/run/secrets/control_ssh_key"))

    assert "/run/secrets/control_ssh_key" not in redacted["stdout"]
    assert "OPENSSH PRIVATE KEY" not in redacted["stdout"]


def test_redacts_nested_runner_result_values() -> None:
    event = {
        "event_data": {
            "res": {
                "stderr": "identity /run/secrets/control_ssh_key\n-----BEGIN RSA PRIVATE KEY-----\nsecret",
            },
        },
    }

    redacted = redact_event(event, Path("/run/secrets/control_ssh_key"))

    assert "/run/secrets/control_ssh_key" not in json.dumps(redacted)
    assert "RSA PRIVATE KEY" not in json.dumps(redacted)


def test_redacts_configured_sensitive_values_recursively() -> None:
    event = {"stdout": "sudo-secret", "event_data": {"res": {"stderr": "password=sudo-secret"}}}

    redacted = redact_event(event, Path("/tmp/host-key"), sensitive_values=["sudo-secret"])

    assert "sudo-secret" not in json.dumps(redacted)
    assert "[REDACTED_SECRET]" in json.dumps(redacted)
