"""비밀번호 해시와 로그인 토큰(JWT). 토큰은 httpOnly 쿠키로만 주고받는다."""

from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from fastapi import Response

from app.core.config import settings

ACCESS_TOKEN_COOKIE = "access_token"
_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        return False


def create_access_token(user_id: int) -> str:
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.access_token_expire_minutes)
    return jwt.encode(
        {"sub": str(user_id), "exp": expires_at}, settings.secret_key, algorithm=_ALGORITHM
    )


def decode_access_token(token: str) -> int | None:
    """유효하면 사용자 id, 만료·위조면 None"""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[_ALGORITHM])
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None


def set_access_token_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=ACCESS_TOKEN_COOKIE,
        value=token,
        max_age=settings.access_token_expire_minutes * 60,
        httponly=True,  # JS에서 읽을 수 없게
        secure=settings.is_production,  # 배포(HTTPS)에서만 Secure
        samesite="lax",
        path="/",
    )


def delete_access_token_cookie(response: Response) -> None:
    response.delete_cookie(
        key=ACCESS_TOKEN_COOKIE,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        path="/",
    )
