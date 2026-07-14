import copy
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import ansible_runner


PRIVATE_KEY_BLOCK = re.compile(r"-----BEGIN OPENSSH PRIVATE KEY-----[\s\S]*", re.DOTALL)


@dataclass(frozen=True)
class RunnerRequest:
    private_data_dir: Path
    inventory: dict
    extravars: dict
    check: bool


@dataclass(frozen=True)
class RunnerResult:
    status: str
    rc: int
    events: list[dict]


def redact_event(event: dict, key_path: Path) -> dict:
    redacted = copy.deepcopy(event)
    stdout = redacted.get("stdout")
    if isinstance(stdout, str):
        stdout = stdout.replace(str(key_path), "[REDACTED_KEY_PATH]")
        redacted["stdout"] = PRIVATE_KEY_BLOCK.sub("[REDACTED_PRIVATE_KEY]", stdout)
    return redacted


def run_playbook(request: RunnerRequest, on_event: Callable[[dict], None], key_path: Path) -> RunnerResult:
    events: list[dict] = []

    def handle_event(event: dict) -> bool:
        safe_event = redact_event(event, key_path)
        events.append(safe_event)
        on_event(safe_event)
        return True

    result = ansible_runner.run(
        private_data_dir=str(request.private_data_dir),
        playbook="playbook.yml",
        inventory=request.inventory,
        extravars=request.extravars,
        event_handler=handle_event,
        quiet=True,
        cmdline="--check" if request.check else None,
    )
    return RunnerResult(status=result.status, rc=result.rc, events=events)
