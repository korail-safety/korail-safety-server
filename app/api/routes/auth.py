from typing import Annotated

from fastapi import APIRouter, Query, Request, Response, status

from app.api.deps import CurrentUser, DbSession
from app.core.rate_limit import RateLimiter
from app.core.security import (
    create_access_token,
    delete_access_token_cookie,
    set_access_token_cookie,
)
from app.schemas.auth import CheckIdResponse, LoginId, LoginRequest, MeResponse, SignupRequest
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])

# 관리자 코드가 하나뿐이라 대입 공격 방지: IP당 10분에 10회
signup_limiter = RateLimiter(max_requests=10, window_seconds=600)
# 비밀번호 대입 방지: IP당 1분에 20회
login_limiter = RateLimiter(max_requests=20, window_seconds=60)


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.get("/check-id", response_model=CheckIdResponse)
def check_id(db: DbSession, id: Annotated[LoginId, Query()]) -> CheckIdResponse:
    """아이디 중복 확인. 중복이어도 에러가 아니라 available: false"""
    return CheckIdResponse(available=not auth_service.is_login_id_taken(db, id))


@router.post("/signup", status_code=status.HTTP_201_CREATED)
def signup(body: SignupRequest, request: Request, db: DbSession) -> None:
    signup_limiter.check(_client_ip(request))
    auth_service.signup(db, body)


@router.post("/login", response_model=MeResponse)
def login(body: LoginRequest, request: Request, response: Response, db: DbSession) -> MeResponse:
    login_limiter.check(_client_ip(request))
    user = auth_service.authenticate(db, body.id, body.password)
    set_access_token_cookie(response, create_access_token(user.id))
    return MeResponse(id=user.login_id, name=user.name)


@router.post("/logout")
def logout(response: Response) -> None:
    """이미 로그아웃 상태여도 200"""
    delete_access_token_cookie(response)


@router.get("/me", response_model=MeResponse)
def me(user: CurrentUser) -> MeResponse:
    return MeResponse(id=user.login_id, name=user.name)
