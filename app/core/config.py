from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """환경변수 설정. 값은 .env 파일이나 실제 환경변수에서 읽는다 (.env.example 참고)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # 실행 환경: local(자동으로 low) / production
    app_env: str = "local"

    # PostgreSQL 접속 주소 (SQLAlchemy 형식)
    database_url: str = "postgresql+psycopg://korail:korail@localhost:5432/korail_safety"

    # CORS 허용 프론트 주소. 쿠키 인증이라 * 는 쓸 수 없다
    frontend_origins: list[str] = Field(default=["http://localhost:3000"])

    # 회원가입 공용 관리자 코드 (프론트로 절대 내려보내지 않는다)
    admin_signup_code: str = "change-me"

    # OpenAI API 키 (분석 API에서 사용, 프론트로 절대 내려보내지 않는다)
    openai_api_key: str = ""

    # 로그인 토큰 서명 키
    secret_key: str = "change-me"
    # 로그인 유지 시간(분)
    access_token_expire_minutes: int = 60 * 24 * 7

    # 파일 저장소 (AWS S3). DB에는 S3 키(경로)만 저장한다
    # 키를 비워 두면 boto3 기본 방식(EC2 IAM 역할 등)으로 인증한다
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = "ap-southeast-2"
    s3_bucket: str = ""
    # 브라우저에 주는 임시 파일 주소(presigned URL) 유효 시간(초)
    presigned_url_expire_seconds: int = 60 * 60

    # 보고서 업로드 최대 크기(MB)
    max_report_size_mb: int = 20

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
