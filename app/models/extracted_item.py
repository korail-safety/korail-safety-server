import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.enums import ExtractedField, varchar_enum


class ExtractedItem(Base):
    """AI가 보고서에서 추출한 항목 (사고 개요·원인·조치 사항·재발 방지 대책)"""

    __tablename__ = "extracted_items"
    __table_args__ = (UniqueConstraint("video_id", "field_key"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    video_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"))
    field_key: Mapped[ExtractedField] = mapped_column(
        varchar_enum(ExtractedField, "field_key", length=30)
    )
    # 현재 값 (사용자 수정 반영)
    content: Mapped[str] = mapped_column(Text)
    # AI가 처음 뽑은 값 (비교·품질 검수용)
    ai_content: Mapped[str] = mapped_column(Text)
    source_page: Mapped[int | None] = mapped_column(Integer)
    source_text: Mapped[str | None] = mapped_column(Text)
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
