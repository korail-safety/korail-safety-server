import secrets

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError
from app.core.security import hash_password, verify_password
from app.models import User
from app.schemas.auth import SignupRequest


def is_login_id_taken(db: Session, login_id: str) -> bool:
    return db.scalar(select(User.id).where(User.login_id == login_id)) is not None


def signup(db: Session, body: SignupRequest) -> User:
    # 관리자 코드 비교 (시간 차이로 코드를 추측하지 못하게 compare_digest 사용)
    if not secrets.compare_digest(body.admin_code, settings.admin_signup_code):
        raise AppError(400, "INVALID_ADMIN_CODE", "유효하지 않은 관리자 코드입니다.")

    # 중복 확인 후 다른 사람이 먼저 가입했을 수 있으니 다시 확인
    if is_login_id_taken(db, body.id):
        raise AppError(409, "ID_DUPLICATED", "이미 사용 중인 아이디입니다.")
    email = body.email.lower()
    if db.scalar(select(User.id).where(User.email == email)) is not None:
        raise AppError(409, "EMAIL_DUPLICATED", "이미 가입된 이메일입니다.")

    user = User(
        login_id=body.id,
        password_hash=hash_password(body.password),
        name=body.name,
        email=email,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        # 동시에 같은 아이디로 가입한 경우 (DB UNIQUE 제약)
        db.rollback()
        raise AppError(409, "ID_DUPLICATED", "이미 사용 중인 아이디입니다.") from exc
    return user


def authenticate(db: Session, login_id: str, password: str) -> User:
    user = db.scalar(select(User).where(User.login_id == login_id))
    # 아이디가 없는 경우와 비밀번호가 틀린 경우를 구분하지 않는다
    if user is None or not verify_password(password, user.password_hash):
        raise AppError(401, "INVALID_CREDENTIALS", "아이디 또는 비밀번호를 확인해 주세요.")
    return user
