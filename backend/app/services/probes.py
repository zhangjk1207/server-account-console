from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Host
from app.services.hosts import HostProbeResult, apply_probe_result, probe_host


def probe_all_hosts(
    session_factory: sessionmaker[Session] | Callable[[], Session],
    *,
    is_job_running: Callable[[], bool],
    probe: Callable[[Host], HostProbeResult] = probe_host,
) -> int:
    """Probe active hosts unless a configuration task owns the SSH runner."""
    if is_job_running():
        return 0

    probed = 0
    with session_factory() as session:
        hosts = list(session.scalars(select(Host).where(Host.archived.is_(False))))
        for host in hosts:
            if is_job_running():
                break
            apply_probe_result(host, probe(host))
            probed += 1
        session.commit()
    return probed
