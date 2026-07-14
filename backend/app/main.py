from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from app.api.auth import router as auth_router
from app.api.health import router as health_router
from app.api.hosts import router as hosts_router
from app.api.scripts import router as scripts_router
from app.api.users import router as users_router
from app.core.config import get_settings

app = FastAPI(title="Server Account Console")
app.add_middleware(
    SessionMiddleware,
    secret_key=get_settings().session_secret,
    https_only=False,
    same_site="lax",
)
app.include_router(auth_router, prefix="/api")
app.include_router(health_router, prefix="/api")
app.include_router(hosts_router, prefix="/api")
app.include_router(users_router, prefix="/api")
app.include_router(scripts_router, prefix="/api")
