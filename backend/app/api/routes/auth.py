from datetime import datetime

from fastapi import APIRouter, Header, HTTPException, Request, Response
from app.core.config import get_settings

from app.core.security import authenticate_credentials, create_access_token, decode_access_token
from app.schemas.auth import LoginIn, LoginOut, MeOut


router = APIRouter()


@router.post("/login", response_model=LoginOut)
def login(payload: LoginIn, request: Request, response: Response):
    user = authenticate_credentials(username=payload.username, password=payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Usuário ou senha inválidos")
    token_data = create_access_token(username=user["username"], role=user["role"])
    settings = get_settings()
    expires_at_raw = token_data["expires_at"]
    expires_dt: datetime | None = None
    try:
        expires_dt = datetime.fromisoformat(expires_at_raw)
    except Exception:
        expires_dt = None
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=token_data["access_token"],
        httponly=True,
        secure=bool(settings.auth_cookie_secure),
        samesite="lax",
        expires=expires_dt,
        path="/",
    )
    return {
        "authenticated": True,
        "expires_at": token_data["expires_at"],
        "user": user,
    }


@router.get("/me", response_model=MeOut)
def me(
    request: Request,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if not token:
        settings = get_settings()
        token = request.cookies.get(settings.auth_cookie_name)
    if not token:
        return {"authenticated": False, "user": None}
    payload = decode_access_token(token)
    if not payload:
        return {"authenticated": False, "user": None}
    return {
        "authenticated": True,
        "user": {
            "username": payload.get("sub"),
            "role": payload.get("role"),
        },
    }


@router.post("/logout")
def logout(response: Response):
    settings = get_settings()
    response.delete_cookie(settings.auth_cookie_name, path="/")
    return {"status": "ok"}
