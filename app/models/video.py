import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, false
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import VideoStage, varchar_enum

if TYPE_CHECKING:
    from app.models.accident_type import AccidentType
    from app.models.report import Report


class Video(TimestampMixin, Base):
    """영상 작업 1개. 업로드 때 만들어져 단계가 진행되고, 저장하면 라이브러리 영상이 된다.

    - 라이브러리: stage = COMPLETED
    - 임시저장: is_draft = true AND stage IN (ANALYSIS, STORYBOARD, GENERATION)
    """

    __tablename__ = "videos"
    __table_args__ = (Index("ix_videos_created_by_stage", "created_by", "stage"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    created_by: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    accident_type_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("accident_types.id", ondelete="RESTRICT"), index=True
    )
    stage: Mapped[VideoStage] = mapped_column(
        varchar_enum(VideoStage, "stage"), default=VideoStage.UPLOADED
    )
    title: Mapped[str | None] = mapped_column(String(100))
    is_draft: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    draft_saved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    video_key: Mapped[str | None] = mapped_column(String(500))
    thumbnail_key: Mapped[str | None] = mapped_column(String(500))
    duration_sec: Mapped[int | None] = mapped_column(Integer)
    saved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    accident_type: Mapped["AccidentType | None"] = relationship()
    report: Mapped["Report | None"] = relationship(
        back_populates="video", uselist=False, passive_deletes=True
    )
