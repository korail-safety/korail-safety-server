from datetime import datetime
from enum import StrEnum

from app.schemas.base import CamelModel


class DraftStep(StrEnum):
    """임시저장 작업이 멈춘 단계 (프론트 DRAFT_STEP과 같은 값).

    영상 생성 중(GENERATION)에 나간 작업은 STORYBOARD로 보여준다.
    """

    ANALYSIS = "ANALYSIS"
    STORYBOARD = "STORYBOARD"


class DraftVideo(CamelModel):
    id: str
    # 보고서 제목 (분석 전이면 보고서 파일명)
    title: str
    updated_at: datetime
    step: DraftStep
    # 그 단계 작업(분석·스토리보드 생성)이 실패했는지 → 화면에 "오류 발생"
    failed: bool


class DraftsResponse(CamelModel):
    items: list[DraftVideo]
