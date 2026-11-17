from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """환경변수 설정. 값은 .env 파일이나 실제 환경변수에서 읽는다 (.env.example 참고)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # 실행 환경: local / production
    app_env: str = "local"

    # PostgreSQL 접속 주소 (SQLAlchemy 형식)
    database_url: str = "postgresql+psycopg://korail:korail@localhost:5432/korail_safety"

    # CORS 허용 프론트 주소. 쿠키 인증이라 * 는 쓸 수 없다
    frontend_origins: list[str] = Field(default=["http://localhost:3000"])

    # 회원가입 공용 관리자 코드 (프론트로 절대 내려보내지 않는다)
    admin_signup_code: str = "change-me"

    # 로그인 토큰 서명 키
    secret_key: str = "change-me"
    # 로그인 유지 시간(분)
    access_token_expire_minutes: int = 60 * 24 * 7

    # 업로드 파일 저장 위치 (로컬 디스크). 나중에 S3로 바꿀 수 있게 경로만 DB에 저장
    upload_dir: str = "storage"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
