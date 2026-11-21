from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.analysis_service import run_analysis
from app.ai.schemas import AnalyzeStartResponse, AnalyzeStatusResponse
from app.api.deps import CurrentUser
from app.core.database import get_db
from app.core.errors import AppError
from app.models.enums import JobStatus, JobType, VideoStage
from app.models.job import Job
from app.models.report import Report
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
