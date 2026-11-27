from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.core.errors import register_error_handlers
from app.services.job_recovery import fail_interrupted_jobs


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # 서버가 켜질 때: 재시작으로 끊긴 AI 작업(IN_PROGRESS)을 실패로 바꾼다
    fail_interrupted_jobs()
    yield


app = FastAPI(
    title="Korail Safety API",
    description="생성형 AI 기반 철도 안전교육 영상 자동화 서비스 API",
    version="0.1.0",
    # 배포 환경에서는 API 문서 페이지를 숨긴다
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.frontend_origins,
    # 로그인 쿠키를 주고받기 위해 필요
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_error_handlers(app)
app.include_router(api_router)
