from fastapi import APIRouter

from app.api.routes import accident_types, ai, auth, health, library, reports

# 기능별 라우터를 여기에 추가한다 (auth, videos, library, drafts, accident_types ...)
api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(accident_types.router)
api_router.include_router(reports.router)
api_router.include_router(library.router)
api_router.include_router(ai.router) #파일 업로드하면 AI 호출.