import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.enums import JobStatus, JobType, varchar_enum


class Job(Base):
    """AI 작업(분석·스토리보드·영상 생성) 실행 기록.

    다시 시도하면 새 행을 추가하고, 가장 최근 행이 현재 상태다.
    """

    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_video_id_type_started_at", "video_id", "type", "started_at"),
        CheckConstraint("progress BETWEEN 0 AND 100", name="progress_range"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    video_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"))
    type: Mapped[JobType] = mapped_column(varchar_enum(JobType, "type"))
    status: Mapped[JobStatus] = mapped_column(
        varchar_enum(JobStatus, "status"), default=JobStatus.IN_PROGRESS
    )
    step: Mapped[str | None] = mapped_column(String(30))
    error_code: Mapped[str | None] = mapped_column(String(20))
    progress: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
