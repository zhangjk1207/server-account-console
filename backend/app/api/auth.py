from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.core.security import csrf_token, require_admin, require_csrf, verify_admin_password
from app.schemas.auth import AuthenticationStatus, LoginRequest

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/login", status_code=status.HTTP_204_NO_CONTENT)
def login(payload: LoginRequest, request: Request) -> Response:
    if not verify_admin_password(payload.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="管理员密码错误")

    request.session["authenticated"] = True
    csrf_token(request)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=AuthenticationStatus)
def me(_: None = Depends(require_admin)) -> AuthenticationStatus:
    return AuthenticationStatus(authenticated=True)


@router.get("/csrf")
def get_csrf(request: Request, _: None = Depends(require_admin)) -> dict[str, str]:
    return {"token": csrf_token(request)}


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, _: None = Depends(require_admin), __: None = Depends(require_csrf)) -> Response:
    request.session.clear()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
