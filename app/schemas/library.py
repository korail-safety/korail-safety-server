from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import StringConstraints

from app.schemas.accident_type import AccidentTypeName, AccidentTypeResponse
from app.schemas.base import CamelModel

# 앞뒤 공백을 지운 뒤 1~100자 (DB videos.title VARCHAR(100))
VideoTitle = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class SortOrder(StrEnum):
    """라이브러리 정렬 (프론트 SORT_ORDER와 같은 값)"""

    LATEST = "LATEST"
    OLDEST = "OLDEST"


class LibraryVideo(CamelModel):
    """라이브러리 목록 카드 1개"""

    id: str
    title: str
    thumbnail_url: str | None = None
    updated_at: datetime
    # 유형이 없으면 null (미분류)
    accident_type: AccidentTypeResponse | None


class LibraryVideoDetail(LibraryVideo):
    """라이브러리 상세. URL은 presigned URL이라 일정 시간 뒤 만료된다."""

    # 화면에서 재생할 주소
    video_url: str | None = None
    # 누르면 "제목.mp4"로 저장되는 주소
    download_url: str | None = None
    duration_sec: int


class LibraryVideosResponse(CamelModel):
    items: list[LibraryVideo]
    # 검색·필터와 상관없는 본인 전체 영상 수 ("전체 N")
    total_count: int


class UpdateVideoInfoRequest(CamelModel):
    """영상 이름·사고 유형 수정. 없는 유형 이름이면 서버가 새로 만든다."""

    file_name: VideoTitle
    accident_type_name: AccidentTypeName
