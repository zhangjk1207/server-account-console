from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Host, HostCredential
from app.services.credentials import CredentialConfigurationError
from app.services.host_connections import CredentialProbeResult, apply_credential_probe, test_host_credential
from app.services.hosts import HostProbeResult, apply_probe_result


def probe_all_hosts(
    session_factory: sessionmaker[Session] | Callable[[], Session],
    *,
    is_job_running: Callable[[], bool],
    probe: Callable[[Host], HostProbeResult] | None = None,
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
            if probe is not None:
                apply_probe_result(host, probe(host))
                probed += 1
                continue
            if session.query(HostCredential.id).filter(HostCredential.host_id == host.id).one_or_none() is None:
                continue
            try:
                result = test_host_credential(session, host)
            except (CredentialConfigurationError, ValueError) as error:
                result = CredentialProbeResult(None, False, False, False, str(error), None)
            apply_credential_probe(session, host, result)
            probed += 1
        session.commit()
    return probed
