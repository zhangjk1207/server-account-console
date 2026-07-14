import copy
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import ansible_runner


PRIVATE_KEY_BLOCK = re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*", re.DOTALL)


@dataclass(frozen=True)
class RunnerRequest:
    private_data_dir: Path
    inventory: dict
    extravars: dict
    check: bool
    playbook: str = "playbook.yml"
    sensitive_values: tuple[str, ...] = ()
    timeout: int = 1200
    forks: int = 5


@dataclass(frozen=True)
class RunnerResult:
    status: str
    rc: int
    events: list[dict]


def redact_event(event: dict, key_path: Path, *, sensitive_values: list[str] | tuple[str, ...] = ()) -> dict:
    def redact(value):
        if isinstance(value, str):
            value = value.replace(str(key_path), "[REDACTED_KEY_PATH]")
            for secret in sensitive_values:
                if secret:
                    value = value.replace(secret, "[REDACTED_SECRET]")
            return PRIVATE_KEY_BLOCK.sub("[REDACTED_PRIVATE_KEY]", value)
        if isinstance(value, dict):
            return {key: redact(item) for key, item in value.items()}
        if isinstance(value, list):
            return [redact(item) for item in value]
        return value

    return redact(copy.deepcopy(event))


def run_playbook(request: RunnerRequest, on_event: Callable[[dict], None], key_path: Path) -> RunnerResult:
    events: list[dict] = []

    def handle_event(event: dict) -> bool:
        safe_event = redact_event(event, key_path, sensitive_values=request.sensitive_values)
        events.append(safe_event)
        on_event(safe_event)
        return True

    result = ansible_runner.run(
        private_data_dir=str(request.private_data_dir),
        playbook=request.playbook,
        inventory=request.inventory,
        extravars=request.extravars,
        event_handler=handle_event,
        quiet=True,
        cmdline=f"{'--check ' if request.check else ''}-f {request.forks}",
        timeout=request.timeout,
    )
    return RunnerResult(status=result.status, rc=result.rc, events=events)
