import uuid

from app.schemas.base import CamelModel


class UploadReportResponse(CamelModel):
    """보고서 업로드·교체 응답 { videoId }"""

    video_id: uuid.UUID
