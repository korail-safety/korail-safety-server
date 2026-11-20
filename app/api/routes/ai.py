from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.analysis_service import run_analysis
from app.ai.schemas import AnalyzeStartResponse, AnalyzeStatusResponse
from app.core.database import get_db
from app.models.enums import JobStatus, JobType
from app.models.job import Job
from app.models.report import Report
from app.models.video import Video

router = APIRouter(prefix="/videos", tags=["ai"])


@router.post("/{video_id}/analyze", response_model=AnalyzeStartResponse)
def start_analysis(video_id: UUID, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    video = db.get(Video, video_id)
    if video is None:
        raise HTTPException(404, detail={"code": "VIDEO_NOT_FOUND", "message": "영상을 찾을 수 없습니다."})

    report = db.scalar(select(Report).where(Report.video_id == video_id))
    if report is None:
        raise HTTPException(404, detail={"code": "REPORT_NOT_FOUND", "message": "보고서가 아직 업로드되지 않았습니다."})

    job = Job(video_id=video_id, type=JobType.ANALYSIS, status=JobStatus.IN_PROGRESS)
    db.add(job)
    db.commit()
    db.refresh(job)

    background_tasks.add_task(run_analysis, video_id, report.id, job.id)
    return AnalyzeStartResponse(job_id=job.id, status=job.status)


@router.get("/{video_id}/analyze", response_model=AnalyzeStatusResponse)
def get_analysis_status(video_id: UUID, db: Session = Depends(get_db)):
    job = db.scalar(
        select(Job).where(Job.video_id == video_id, Job.type == JobType.ANALYSIS).order_by(Job.started_at.desc())
    )
    if job is None:
        raise HTTPException(404, detail={"code": "JOB_NOT_FOUND", "message": "분석 작업이 없습니다."})
    return AnalyzeStatusResponse(status=job.status, error_code=job.error_code)