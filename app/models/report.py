import uuid
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, Identity, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin

if TYPE_CHECKING:
    from app.models.video import Video


class Report(CreatedAtMixin, Base):
    """업로드한 사고 보고서 (영상 1개당 1개)"""

    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    video_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"), unique=True
    )
    original_file_name: Mapped[str] = mapped_column(String(255))
    file_key: Mapped[str] = mapped_column(String(500))
    file_size: Mapped[int] = mapped_column(BigInteger)
    mime_type: Mapped[str] = mapped_column(String(100))
    page_count: Mapped[int | None] = mapped_column(Integer)

    video: Mapped["Video"] = relationship(back_populates="report")
    pages: Mapped[list["ReportPage"]] = relationship(
        back_populates="report", order_by="ReportPage.page_no", passive_deletes=True
    )


class ReportPage(Base):
    """보고서에서 추출한 페이지별 텍스트 (원문 보기용)"""

    __tablename__ = "report_pages"
    __table_args__ = (UniqueConstraint("report_id", "page_no"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    report_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("reports.id", ondelete="CASCADE"))
    page_no: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    image_key: Mapped[str | None] = mapped_column(String(500))

    report: Mapped[Report] = relationship(back_populates="pages")
