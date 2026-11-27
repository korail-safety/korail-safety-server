from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.analysis_service import run_analysis
#분석용
from app.ai.schemas import (
    AnalysisResultResponse,
    AnalyzeStartResponse,
    AnalyzeStatusResponse,
    ExtractedItemResponse,
    ExtractedSource,
    ReportPageResponse,
    UpdateItemRequest,
)
from app.api.deps import CurrentUser
from app.core import storage
from app.core.database import get_db
from app.core.errors import AppError
from app.models.enums import ExtractedField, JobStatus, JobType, VideoStage
from app.models.extracted_item import ExtractedItem
from app.models.job import Job
from app.models.report import Report, ReportPage
from app.models.video import Video
#스토리보드용
from app.ai.storyboard_schemas import StoryboardResponse, StoryboardRevisionRequest, StoryboardScene 
from app.ai.storyboard_service import generate_storyboard, regenerate_scene_image 
from app.models.storyboard import Storyboard #DB 모델

def _to_response(item: ExtractedItem) -> ExtractedItemResponse:
    """ExtractedItem.source_rects(JSON)를 sources 목록 + 구버전 호환 필드로 변환."""
    raw: list[dict] = item.source_rects or []
    if raw and "page" in raw[0]:
        # 새 형식: 근거 목록 [{page, text, rects}]
        sources = [ExtractedSource(**s) for s in raw]
        legacy_rects = raw[0].get("rects")
    else:
        # 예전 형식(근거 여러 개 지원 전에 분석한 작업): 좌표 목록 [{x, y, width, height}]만 있음
        # → 기존 source_page·source_text와 묶어서 근거 1개로 감싼다
        legacy_rects = raw or None
        sources = (
            [
                ExtractedSource(
                    page=item.source_page, text=item.source_text or "", rects=legacy_rects
                )
            ]
            if item.source_page
            else []
        )
    return ExtractedItemResponse(
        field_key=item.field_key,
        content=item.content,
        ai_content=item.ai_content,
        source_page=item.source_page,
        source_text=item.source_text,
        source_rects=legacy_rects,
        sources=sources,
        edited_at=item.edited_at,
    )


router = APIRouter(prefix="/videos", tags=["ai"])


@router.post("/{video_id}/analysis", response_model=AnalyzeStartResponse)
def start_analysis(
    video_id: UUID,
    background_tasks: BackgroundTasks,
    user: CurrentUser,
    db: Session = Depends(get_db),
):
    video = db.get(Video, video_id)
    if video is None:
        raise AppError(404, "VIDEO_NOT_FOUND", "영상을 찾을 수 없습니다.")
    if video.created_by != user.id:
        raise AppError(403, "FORBIDDEN", "본인 영상만 접근할 수 있습니다.")

    report = db.scalar(select(Report).where(Report.video_id == video_id))
    if report is None:
        raise AppError(404, "REPORT_NOT_FOUND", "보고서가 아직 업로드되지 않았습니다.")

    job = Job(video_id=video_id, type=JobType.ANALYSIS, status=JobStatus.IN_PROGRESS)
    db.add(job)
    video.stage = VideoStage.ANALYSIS
    db.commit()
    db.refresh(job)

    background_tasks.add_task(run_analysis, video_id, report.id, job.id)
    return AnalyzeStartResponse(job_id=job.id, status=job.status)


@router.get("/{video_id}/analysis", response_model=AnalyzeStatusResponse)
def get_analysis_status(video_id: UUID, user: CurrentUser, db: Session = Depends(get_db)):
    video = db.get(Video, video_id)
    if video is None:
        raise AppError(404, "VIDEO_NOT_FOUND", "영상을 찾을 수 없습니다.")
    if video.created_by != user.id:
        raise AppError(403, "FORBIDDEN", "본인 영상만 접근할 수 있습니다.")

    job = db.scalar(
        select(Job)
        .where(Job.video_id == video_id, Job.type == JobType.ANALYSIS)
        .order_by(Job.started_at.desc())
    )
    if job is None:
        raise AppError(404, "JOB_NOT_FOUND", "분석 작업이 없습니다.")
    return AnalyzeStatusResponse(status=job.status, step=job.step, error_code=job.error_code)


@router.get("/{video_id}/analysis/result", response_model=AnalysisResultResponse)
def get_analysis_result(video_id: UUID, user: CurrentUser, db: Session = Depends(get_db)):
    video = db.get(Video, video_id)
    if video is None:
        raise AppError(404, "VIDEO_NOT_FOUND", "영상을 찾을 수 없습니다.")
    if video.created_by != user.id:
        raise AppError(403, "FORBIDDEN", "본인 영상만 접근할 수 있습니다.")

    report = db.scalar(select(Report).where(Report.video_id == video_id))
    if report is None:
        raise AppError(404, "REPORT_NOT_FOUND", "보고서가 아직 업로드되지 않았습니다.")
    # 업로드 때 저장한 페이지 수. 없으면 분석 때 저장한 페이지 수로 대신한다
    total_pages = report.page_count or db.scalar(
        select(func.count()).select_from(ReportPage).where(ReportPage.report_id == report.id)
    )

    items = db.scalars(select(ExtractedItem).where(ExtractedItem.video_id == video_id)).all()
    # 화면에 보여줄 순서(사고 개요 → 원인 → 조치 → 재발 방지)대로 정렬
    order = list(ExtractedField)
    items = sorted(items, key=lambda i: order.index(i.field_key))
    return AnalysisResultResponse(
        total_pages=total_pages or 0,
        items=[_to_response(i) for i in items],
    )


@router.get("/{video_id}/report/pages/{page}", response_model=ReportPageResponse)
def get_report_page(video_id: UUID, page: int, user: CurrentUser, db: Session = Depends(get_db)):
    video = db.get(Video, video_id)
    if video is None:
        raise AppError(404, "VIDEO_NOT_FOUND", "영상을 찾을 수 없습니다.")
    if video.created_by != user.id:
        raise AppError(403, "FORBIDDEN", "본인 영상만 접근할 수 있습니다.")

    report = db.scalar(select(Report).where(Report.video_id == video_id))
    if report is None:
        raise AppError(404, "REPORT_NOT_FOUND", "보고서가 아직 업로드되지 않았습니다.")

    report_page = db.scalar(
        select(ReportPage).where(ReportPage.report_id == report.id, ReportPage.page_no == page)
    )
    if report_page is None:
        raise AppError(404, "PAGE_NOT_FOUND", "해당 페이지를 찾을 수 없습니다.")
    image_url = storage.presigned_url(report_page.image_key) if report_page.image_key else None
    return ReportPageResponse(
        page_no=report_page.page_no, text=report_page.text, image_url=image_url
    )


@router.patch("/{video_id}/analysis/result/items/{key}", response_model=ExtractedItemResponse)
def update_extracted_item(
    video_id: UUID,
    key: str,
    body: UpdateItemRequest,
    user: CurrentUser,
    db: Session = Depends(get_db),
):
    video = db.get(Video, video_id)
    if video is None:
        raise AppError(404, "VIDEO_NOT_FOUND", "영상을 찾을 수 없습니다.")
    if video.created_by != user.id:
        raise AppError(403, "FORBIDDEN", "본인 영상만 접근할 수 있습니다.")

    try:
        field_enum = ExtractedField(key.upper())
    except ValueError:
        raise AppError(400, "INVALID_INPUT", "알 수 없는 항목 키입니다.") from None

    item = db.scalar(
        select(ExtractedItem).where(
            ExtractedItem.video_id == video_id, ExtractedItem.field_key == field_enum
        )
    )
    if item is None:
        raise AppError(404, "ITEM_NOT_FOUND", "항목을 찾을 수 없습니다.")

    item.content = body.content
    item.edited_at = datetime.now(UTC)
    db.commit()
    db.refresh(item)
    return _to_response(item)

@router.get("/{video_id}/storyboard", response_model=StoryboardResponse)
def get_storyboard(video_id: UUID, user: CurrentUser, db: Session = Depends(get_db)):
    video = db.get(Video, video_id)
    if video is None:
        raise AppError(404, "VIDEO_NOT_FOUND", "영상을 찾을 수 없습니다.")
    if video.created_by != user.id:
        raise AppError(403, "FORBIDDEN", "본인 영상만 접근할 수 있습니다.")

    latest_rev = (
        select(Storyboard.scene_index, func.max(Storyboard.revision).label("max_rev"))
        .where(Storyboard.video_id == video_id)
        .group_by(Storyboard.scene_index)
        .subquery()
    )
    storyboard_rows = db.scalars(
        select(Storyboard)
        .join(
            latest_rev,
            (Storyboard.scene_index == latest_rev.c.scene_index)
            & (Storyboard.revision == latest_rev.c.max_rev),
        )
        .where(Storyboard.video_id == video_id)
        .order_by(Storyboard.scene_index)
    ).all()

    if not storyboard_rows:
        setup_job = db.scalar(
            select(Job)
            .where(Job.video_id == video_id, Job.type == JobType.STORYBOARD, Job.scene_index.is_(None))
            .order_by(Job.started_at.desc())
        )
        if setup_job is None:
            raise AppError(404, "JOB_NOT_FOUND", "스토리보드 생성이 시작되지 않았습니다.")
        return StoryboardResponse(status=setup_job.status, scenes=[], error_code=setup_job.error_code)

    latest_job = (
        select(Job.scene_index, func.max(Job.started_at).label("max_started"))
        .where(Job.video_id == video_id, Job.type == JobType.STORYBOARD)
        .group_by(Job.scene_index)
        .subquery()
    )
    job_by_scene = {
        j.scene_index: j
        for j in db.scalars(
            select(Job)
            .join(
                latest_job,
                (Job.scene_index == latest_job.c.scene_index)
                & (Job.started_at == latest_job.c.max_started),
            )
            .where(Job.video_id == video_id, Job.type == JobType.STORYBOARD)
        ).all()
    }

    scenes = []
    overall_status, overall_error = "COMPLETED", None
    for row in storyboard_rows:
        job = job_by_scene.get(row.scene_index)
        scene_status = job.status if job else "COMPLETED"
        scene_error = job.error_code if job else None
        if scene_status == JobStatus.IN_PROGRESS:
            overall_status = "IN_PROGRESS"
        elif scene_status == JobStatus.FAILED and overall_status != "IN_PROGRESS":
            overall_status, overall_error = "FAILED", scene_error

        scenes.append(
            StoryboardScene(
                index=row.scene_index,
                image_url=storage.presigned_url(row.image_key) if row.image_key else None,
                description=row.description,
                duration_sec=row.duration_sec,
                status=scene_status,
                error_code=scene_error,
            )
        )

    return StoryboardResponse(status=overall_status, scenes=scenes, error_code=overall_error)

@router.post("/{video_id}/storyboard", status_code=202)
def start_storyboard(
    video_id: UUID,
    background_tasks: BackgroundTasks,
    user: CurrentUser,
    db: Session = Depends(get_db),
):
    video = db.get(Video, video_id)
    if video is None:
        raise AppError(404, "VIDEO_NOT_FOUND", "영상을 찾을 수 없습니다.")
    if video.created_by != user.id:
        raise AppError(403, "FORBIDDEN", "본인 영상만 접근할 수 있습니다.")

    existing = db.scalar(
        select(Storyboard.id).where(Storyboard.video_id == video_id).limit(1)
    )
    if existing is not None:
        raise AppError(409, "STORYBOARD_ALREADY_EXISTS", "이미 스토리보드가 생성된 영상입니다.")

    has_analysis = db.scalar(
        select(ExtractedItem.video_id).where(ExtractedItem.video_id == video_id).limit(1)
    )
    if has_analysis is None:
        raise AppError(409, "ANALYSIS_NOT_COMPLETED", "분석 결과가 없습니다.")

    job = Job(video_id=video_id, type=JobType.STORYBOARD, status=JobStatus.IN_PROGRESS)
    db.add(job)
    video.stage = VideoStage.STORYBOARD
    db.commit()
    db.refresh(job)

    background_tasks.add_task(generate_storyboard, video_id, job.id)
    return Response(status_code=202)

@router.post("/{video_id}/storyboard/revisions", status_code=202)
def create_storyboard_revision(
    video_id: UUID,
    body: StoryboardRevisionRequest,
    background_tasks: BackgroundTasks,
    user: CurrentUser,
    db: Session = Depends(get_db),
):
    video = db.get(Video, video_id)
    if video is None:
        raise AppError(404, "VIDEO_NOT_FOUND", "영상을 찾을 수 없습니다.")
    if video.created_by != user.id:
        raise AppError(403, "FORBIDDEN", "본인 영상만 접근할 수 있습니다.")

    in_progress = db.scalar(
        select(Job).where(
            Job.video_id == video_id,
            Job.scene_index == body.scene_index,
            Job.type == JobType.STORYBOARD,
            Job.status == JobStatus.IN_PROGRESS,
        )
    )
    if in_progress is not None:
        raise AppError(409, "STORYBOARD_IN_PROGRESS", "이미 생성 중인 장면입니다.")

    previous = db.scalar(
        select(Storyboard)
        .where(
            Storyboard.video_id == video_id,
            Storyboard.scene_index == body.scene_index,
        )
        .order_by(Storyboard.revision.desc())
    )
    if previous is None:
        raise AppError(400, "INVALID_INPUT", "존재하지 않는 장면 번호입니다.")

    storyboard = Storyboard(
        video_id=video_id,
        scene_index=body.scene_index,
        revision=previous.revision + 1,
        prompt=previous.prompt,
        revision_request=body.prompt,      # 신규: 사용자 수정 요청은 별도 컬럼에
        description=previous.description,  # 신규
        duration_sec=previous.duration_sec,
    )
    db.add(storyboard)

    job = Job(
        video_id=video_id,
        type=JobType.STORYBOARD,
        scene_index=body.scene_index,
        status=JobStatus.IN_PROGRESS,
    )
    db.add(job)
    db.commit()
    db.refresh(storyboard)
    db.refresh(job)

    background_tasks.add_task(
        regenerate_scene_image, video_id, body.scene_index, storyboard.id, job.id, previous.image_key
    )