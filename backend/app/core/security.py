import secrets

import bcrypt
from fastapi import HTTPException, Request, status

from app.core.config import get_settings


def verify_admin_password(password: str) -> bool:
    settings = get_settings()
    return bcrypt.checkpw(password.encode(), settings.admin_password_hash.encode())


def require_admin(request: Request) -> None:
    if request.session.get("authenticated") is not True:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")


def csrf_token(request: Request) -> str:
    token = request.session.get("csrf_token")
    if isinstance(token, str):
        return token

    token = secrets.token_urlsafe(32)
    request.session["csrf_token"] = token
    return token


def require_csrf(request: Request) -> None:
    expected = request.session.get("csrf_token")
    provided = request.headers.get("X-CSRF-Token")
    if not isinstance(expected, str) or not secrets.compare_digest(expected, provided or ""):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF 校验失败")
