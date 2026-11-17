from fastapi import APIRouter

from app.api.routes import health

# 기능별 라우터를 여기에 추가한다 (auth, videos, library, drafts, accident_types ...)
api_router = APIRouter()
api_router.include_router(health.router)
