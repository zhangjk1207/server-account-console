import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from app.api.auth import router as auth_router
from app.api.access_grants import execution_router as access_grant_execution_router
from app.api.access_grants import router as access_grants_router
from app.api.health import router as health_router
from app.api.host_credentials import router as host_credentials_router
from app.api.host_operations import execution_router as host_operation_execution_router
from app.api.host_operations import router as host_operations_router
from app.api.hosts import router as hosts_router
from app.api.jobs import router as jobs_router
from app.api.permission_templates import router as permission_templates_router
from app.api.scripts import router as scripts_router
from app.api.users import router as users_router
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services.backup import backup_sqlite_url
from app.services.jobs import RUNNER_LOCK, expire_ready_previews
from app.services.probes import probe_all_hosts


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()

    async def probe_loop() -> None:
        while True:
            await asyncio.to_thread(probe_all_hosts, SessionLocal, is_job_running=RUNNER_LOCK.locked)
            await asyncio.sleep(settings.host_probe_interval_seconds)

    async def maintenance_loop() -> None:
        while True:
            with SessionLocal() as session:
                expire_ready_previews(session)
            await asyncio.to_thread(backup_sqlite_url, settings.database_url)
            await asyncio.sleep(settings.backup_interval_seconds)

    tasks = [asyncio.create_task(probe_loop()), asyncio.create_task(maintenance_loop())]
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
        for task in tasks:
            with suppress(asyncio.CancelledError):
                await task

app = FastAPI(title="Server Account Console", lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=get_settings().session_secret,
    https_only=False,
    same_site="lax",
)
app.include_router(auth_router, prefix="/api")
app.include_router(health_router, prefix="/api")
app.include_router(hosts_router, prefix="/api")
app.include_router(host_credentials_router, prefix="/api")
app.include_router(host_operations_router, prefix="/api")
app.include_router(host_operation_execution_router, prefix="/api")
app.include_router(jobs_router, prefix="/api")
app.include_router(users_router, prefix="/api")
app.include_router(scripts_router, prefix="/api")
app.include_router(permission_templates_router, prefix="/api")
app.include_router(access_grants_router, prefix="/api")
app.include_router(access_grant_execution_router, prefix="/api")
