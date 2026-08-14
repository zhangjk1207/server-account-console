import copy
import os
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


PRIVATE_KEY_BLOCK = re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*", re.DOTALL)


def _load_ansible_runner() -> Any:
    try:
        import ansible_runner
    except (ImportError, ModuleNotFoundError) as error:
        raise RuntimeError("Ansible execution requires the Linux runtime or container deployment") from error
    return ansible_runner


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
    def redact(value, path: tuple[str, ...] = (), redact_sensitive: bool = True):
        if isinstance(value, str):
            for rendered_path in {str(key_path), key_path.as_posix()}:
                value = value.replace(rendered_path, "[REDACTED_KEY_PATH]")
            if redact_sensitive:
                for secret in sensitive_values:
                    if secret:
                        value = value.replace(secret, "[REDACTED_SECRET]")
            return PRIVATE_KEY_BLOCK.sub("[REDACTED_PRIVATE_KEY]", value)
        if isinstance(value, dict):
            return {
                key: redact(
                    item,
                    path + (str(key),),
                    redact_sensitive and not (path == ("event_data", "res") and key == "msg" and isinstance(item, (dict, list))),
                )
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [redact(item, path, redact_sensitive) for item in value]
        return value

    return redact(copy.deepcopy(event))


def run_playbook(request: RunnerRequest, on_event: Callable[[dict], None], key_path: Path) -> RunnerResult:
    events: list[dict] = []
    runner_script_bin = Path(sys.argv[0]).resolve().parent
    # sys.executable commonly points at a virtualenv symlink. Resolving it loses
    # the virtualenv's bin directory, where ansible-playbook is installed.
    python_bin = Path(sys.executable).parent
    executable = next(
        (
            directory / "ansible-playbook"
            for directory in (python_bin, runner_script_bin)
            if (directory / "ansible-playbook").is_file()
        ),
        None,
    )
    discovered = shutil.which("ansible-playbook")
    ansible_bin = str(executable.parent if executable is not None else Path(discovered).parent if discovered else python_bin)
    runner_path = os.environ.get("PATH", "")

    def handle_event(event: dict) -> bool:
        safe_event = redact_event(event, key_path, sensitive_values=request.sensitive_values)
        events.append(safe_event)
        on_event(safe_event)
        return True

    result = _load_ansible_runner().run(
        private_data_dir=str(request.private_data_dir),
        playbook=request.playbook,
        inventory=request.inventory,
        extravars=request.extravars,
        event_handler=handle_event,
        quiet=True,
        envvars={"PATH": f"{ansible_bin}{os.pathsep}{runner_path}"},
        cmdline=f"{'--check ' if request.check else ''}-f {request.forks}",
        timeout=request.timeout,
    )
    return RunnerResult(status=result.status, rc=result.rc, events=events)
