from typing import Annotated

from fastapi import Cookie, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import AppError
from app.core.security import ACCESS_TOKEN_COOKIE, decode_access_token
from app.models import User

DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(
    db: DbSession,
    access_token: Annotated[str | None, Cookie(alias=ACCESS_TOKEN_COOKIE)] = None,
) -> User:
    """로그인 쿠키로 사용자를 찾는다. 없거나 만료되면 401 UNAUTHORIZED."""
    user_id = decode_access_token(access_token) if access_token else None
    user = db.get(User, user_id) if user_id else None
    if user is None:
        raise AppError(401, "UNAUTHORIZED", "로그인이 필요합니다.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
