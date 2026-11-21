import uuid

from fastapi import APIRouter, Response, status

from app.api.deps import CurrentUser, DbSession
from app.schemas.draft import DraftsResponse, DraftVideo
from app.schemas.library import SortOrder
from app.services import draft as draft_service

router = APIRouter(tags=["drafts"])


@router.post("/videos/{video_id}/draft", status_code=status.HTTP_204_NO_CONTENT)
def save_draft(video_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Response:
    """지금 단계까지 임시저장 (분석 결과·스토리보드 화면의 "임시저장" 버튼)"""
    draft_service.save_draft(db, user.id, video_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/drafts", response_model=DraftsResponse)
def list_drafts(
    user: CurrentUser,
    db: DbSession,
    keyword: str | None = None,
    sort: SortOrder = SortOrder.LATEST,
) -> DraftsResponse:
    """본인 임시저장 목록. keyword(제목 검색), sort(LATEST|OLDEST)"""
    rows = draft_service.list_drafts(db, user.id, keyword, sort)
    return DraftsResponse(
        items=[
            DraftVideo(
                id=str(video.id),
                title=video.title or "",
                updated_at=video.updated_at,
                step=draft_service.to_step(video.stage),
                failed=failed,
            )
            for video, failed in rows
        ]
    )


@router.delete("/drafts/{video_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_draft(video_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Response:
    """임시저장 삭제 (보고서·분석 결과 포함, 복구 불가)"""
    draft_service.delete_draft(db, user.id, video_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
