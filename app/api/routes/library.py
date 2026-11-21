import uuid
from pathlib import PurePath
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.deps import CurrentUser, DbSession
from app.core import storage
from app.models import Video
from app.schemas.accident_type import AccidentTypeResponse
from app.schemas.library import (
    LibraryVideo,
    LibraryVideoDetail,
    LibraryVideosResponse,
    SortOrder,
    UpdateVideoInfoRequest,
)
from app.services import library as library_service

router = APIRouter(prefix="/library/videos", tags=["library"])


def _to_item(video: Video) -> LibraryVideo:
    return LibraryVideo(
        id=str(video.id),
        title=video.title or "",
        thumbnail_url=storage.presigned_url(video.thumbnail_key) if video.thumbnail_key else None,
        updated_at=video.updated_at,
        accident_type=(
            AccidentTypeResponse.model_validate(video.accident_type)
            if video.accident_type
            else None
        ),
    )


def _to_detail(video: Video) -> LibraryVideoDetail:
    video_url = download_url = None
    if video.video_key:
        video_url = storage.presigned_url(video.video_key)
        extension = PurePath(video.video_key).suffix or ".mp4"
        download_url = storage.presigned_url(
            video.video_key, download_filename=f"{video.title or 'video'}{extension}"
        )
    return LibraryVideoDetail(
        **_to_item(video).model_dump(),
        video_url=video_url,
        download_url=download_url,
        duration_sec=video.duration_sec or 0,
    )


@router.get("", response_model=LibraryVideosResponse)
def list_library_videos(
    user: CurrentUser,
    db: DbSession,
    keyword: str | None = None,
    # 프론트가 camelCase(accidentTypeId)로 보낸다
    accident_type_id: Annotated[int | None, Query(alias="accidentTypeId")] = None,
    sort: SortOrder = SortOrder.LATEST,
) -> LibraryVideosResponse:
    """본인 완성 영상 목록. keyword(제목 검색), accidentTypeId(유형 필터), sort(LATEST|OLDEST)"""
    items, total_count = library_service.list_videos(db, user.id, keyword, accident_type_id, sort)
    return LibraryVideosResponse(items=[_to_item(v) for v in items], total_count=total_count)


@router.get("/{video_id}", response_model=LibraryVideoDetail)
def get_library_video(video_id: uuid.UUID, user: CurrentUser, db: DbSession) -> LibraryVideoDetail:
    """완성 영상 상세 (재생 주소 videoUrl, 다운로드 주소 downloadUrl 포함)"""
    return _to_detail(library_service.get_video(db, user.id, video_id))


@router.patch("/{video_id}", response_model=LibraryVideo)
def update_library_video(
    video_id: uuid.UUID, body: UpdateVideoInfoRequest, user: CurrentUser, db: DbSession
) -> LibraryVideo:
    """영상 이름·사고 유형 수정 (없는 유형 이름이면 새로 만든다)"""
    video = library_service.update_info(
        db, user.id, video_id, body.file_name, body.accident_type_name
    )
    return _to_item(video)


@router.delete("/{video_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_library_video(video_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Response:
    """영상 삭제 (DB + S3 파일, 복구 불가)"""
    library_service.delete_video(db, user.id, video_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
