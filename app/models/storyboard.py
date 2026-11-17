import uuid

from sqlalchemy import BigInteger, ForeignKey, Identity, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAtMixin


class Storyboard(CreatedAtMixin, Base):
    """스토리보드. 수정 요청할 때마다 revision을 올려 새 행을 추가한다."""

    __tablename__ = "storyboards"
    __table_args__ = (UniqueConstraint("video_id", "revision"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    video_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"))
    revision: Mapped[int] = mapped_column(Integer)
    # 사용자 수정 요청 (첫 생성은 NULL)
    prompt: Mapped[str | None] = mapped_column(Text)
    image_key: Mapped[str | None] = mapped_column(String(500))
