"""임시저장: 등록·목록·삭제. 본인 작업만 다룬다.

임시저장 = 아직 완성 전(ANALYSIS·STORYBOARD·GENERATION)인 작업.
분석을 시작하면 자동으로 목록에 남는다.
(창을 닫거나 뒤로가기로 나가도 작업이 사라지지 않게. 버리고 싶으면 삭제한다)
완성해서 라이브러리에 저장되면(COMPLETED) 목록에서 자동으로 빠진다.
is_draft·draft_saved_at은 "임시저장" 버튼을 누른 기록으로만 남긴다.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import Job, Video
from app.models.enums import JobStatus, JobType, VideoStage
from app.schemas.library import SortOrder
from app.services.video_files import delete_video_and_files

DRAFT_STAGES = (VideoStage.ANALYSIS, VideoStage.STORYBOARD, VideoStage.GENERATION)


def _get_own(db: Session, user_id: int, video_id: uuid.UUID) -> Video:
    """없으면 404, 남의 작업이면 403"""
    video = db.get(Video, video_id)
    if video is None:
        raise AppError(404, "VIDEO_NOT_FOUND", "영상 작업을 찾을 수 없습니다.")
    if video.created_by != user_id:
        raise AppError(403, "FORBIDDEN", "본인 영상만 접근할 수 있습니다.")
    return video


def save_draft(db: Session, user_id: int, video_id: uuid.UUID) -> None:
    """분석 결과·스토리보드 화면의 "임시저장" 버튼. 여러 번 눌러도 된다."""
    video = _get_own(db, user_id, video_id)
    if video.stage not in DRAFT_STAGES:
        # 분석 전(UPLOADED)이거나 이미 라이브러리에 저장된(COMPLETED) 작업
        raise AppError(409, "INVALID_STAGE", "지금 단계에서는 임시저장할 수 없습니다.")
    video.is_draft = True
    video.draft_saved_at = datetime.now(UTC)
    db.commit()


def _draft_query(user_id: int):
    return select(Video).where(
        Video.created_by == user_id,
        Video.stage.in_(DRAFT_STAGES),
    )


def _latest_jobs(db: Session, video_ids: list[uuid.UUID]) -> dict[tuple[uuid.UUID, JobType], Job]:
    """(영상, 작업 종류)별 가장 최근 작업. 다시 시도하면 새 행이 생기므로 최근 것이 현재 상태"""
    if not video_ids:
        return {}
    jobs = db.scalars(
        select(Job).where(Job.video_id.in_(video_ids)).order_by(Job.started_at, Job.id)
    ).all()
    # 오래된 순으로 덮어써서 마지막(최근) 것만 남긴다
    return {(job.video_id, job.type): job for job in jobs}


def to_step(stage: VideoStage) -> str:
    return "ANALYSIS" if stage == VideoStage.ANALYSIS else "STORYBOARD"


def list_drafts(
    db: Session, user_id: int, keyword: str | None, sort: SortOrder
) -> list[tuple[Video, bool]]:
    """(작업, 실패 여부) 목록"""
    query = _draft_query(user_id)
    if keyword and keyword.strip():
        escaped = keyword.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.where(Video.title.ilike(f"%{escaped}%", escape="\\"))
    order = Video.updated_at.asc() if sort == SortOrder.OLDEST else Video.updated_at.desc()
    videos = list(db.scalars(query.order_by(order, Video.id)).all())

    latest = _latest_jobs(db, [video.id for video in videos])
    result = []
    for video in videos:
        # 생성 단계(GENERATION)는 스토리보드로 돌아가 다시 시작하므로 실패로 보지 않는다
        job_type = {
            VideoStage.ANALYSIS: JobType.ANALYSIS,
            VideoStage.STORYBOARD: JobType.STORYBOARD,
        }.get(video.stage)
        job = latest.get((video.id, job_type)) if job_type else None
        result.append((video, job is not None and job.status == JobStatus.FAILED))
    return result


def delete_draft(db: Session, user_id: int, video_id: uuid.UUID) -> None:
    video = _get_own(db, user_id, video_id)
    if video.stage not in DRAFT_STAGES:
        # 임시저장이 아닌 작업(업로드만 한 작업, 완성된 영상)은 여기서 지우지 않는다
        raise AppError(404, "VIDEO_NOT_FOUND", "임시저장한 작업을 찾을 수 없습니다.")
    # AI 작업이 돌고 있으면 끝난 뒤 지운 작업에 결과를 쓰려다 실패하므로 막는다
    running = db.scalar(
        select(Job.id).where(Job.video_id == video_id, Job.status == JobStatus.IN_PROGRESS).limit(1)
    )
    if running is not None:
        raise AppError(409, "JOB_IN_PROGRESS", "작업이 진행 중이라 삭제할 수 없습니다.")
    delete_video_and_files(db, video)
