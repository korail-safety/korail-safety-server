"""모든 모델을 여기서 불러온다 (Alembic이 테이블 목록을 찾을 수 있게)."""

from app.models.accident_type import AccidentType
from app.models.base import Base
from app.models.extracted_item import ExtractedItem
from app.models.job import Job
from app.models.report import Report, ReportPage
from app.models.storyboard import Storyboard
from app.models.user import User
from app.models.video import Video

__all__ = [
    "AccidentType",
    "Base",
    "ExtractedItem",
    "Job",
    "Report",
    "ReportPage",
    "Storyboard",
    "User",
    "Video",
]
