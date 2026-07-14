from pathlib import Path
import json
import os

from app.services import runner
from app.services.runner import RunnerRequest, redact_event, run_playbook


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


def test_runner_uses_the_current_python_environment_for_ansible(monkeypatch, tmp_path) -> None:
    captured: dict = {}
    ansible_bin = tmp_path / "venv-bin"
    ansible_bin.mkdir()
    (ansible_bin / "ansible-playbook").touch()
    actual_bin = tmp_path / "actual-bin"
    actual_bin.mkdir()
    actual_python = actual_bin / "python"
    actual_python.touch()
    (ansible_bin / "python").symlink_to(actual_python)
    monkeypatch.setattr(runner.sys, "executable", str(ansible_bin / "python"))

    class Result:
        status = "successful"
        rc = 0

    def fake_run(**kwargs):
        captured.update(kwargs)
        return Result()

    monkeypatch.setattr(runner.ansible_runner, "run", fake_run)

    run_playbook(
        RunnerRequest(tmp_path, {}, {}, False),
        lambda _event: None,
        tmp_path / "credential.key",
    )

    assert captured["envvars"]["PATH"].split(os.pathsep)[0] == str(ansible_bin)


def test_preserves_structured_inventory_values_that_match_a_sudo_password() -> None:
    event = {
        "stdout": "sudo password=zhangjikang",
        "event_data": {
            "res": {
                "msg": {
                    "getent_passwd": {
                        "zhangjikang": ["x", "1002", "1002", "", "/home/zhangjikang", "/bin/bash"],
                    },
                },
            },
        },
    }

    redacted = redact_event(event, Path("/tmp/host-key"), sensitive_values=["zhangjikang"])

    assert redacted["stdout"] == "sudo password=[REDACTED_SECRET]"
    assert redacted["event_data"]["res"]["msg"]["getent_passwd"]["zhangjikang"][4] == "/home/zhangjikang"
