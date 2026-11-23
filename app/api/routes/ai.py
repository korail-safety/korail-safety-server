from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.analysis_service import run_analysis
from app.ai.schemas import (
    AnalysisResultResponse,
    AnalyzeStartResponse,
    AnalyzeStatusResponse,
    ExtractedItemResponse,
    ReportPageResponse,
    UpdateItemRequest,
)
from app.api.deps import CurrentUser
from app.core.database import get_db
from app.core.errors import AppError
from app.models.enums import ExtractedField, JobStatus, JobType, VideoStage
from app.models.extracted_item import ExtractedItem
from app.models.job import Job
from app.models.report import Report, ReportPage
from app.models.video import Video

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
        items=[
            ExtractedItemResponse(
                field_key=i.field_key,
                content=i.content,
                ai_content=i.ai_content,
                source_page=i.source_page,
                source_text=i.source_text,
                edited_at=i.edited_at,
            )
            for i in items
        ],
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
    return ReportPageResponse(page_no=report_page.page_no, text=report_page.text)


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
    return ExtractedItemResponse(
        field_key=item.field_key,
        content=item.content,
        ai_content=item.ai_content,
        source_page=item.source_page,
        source_text=item.source_text,
        edited_at=item.edited_at,
    )
