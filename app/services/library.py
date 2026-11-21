"""라이브러리(완성 영상) 조회·수정·삭제. 본인이 만든 COMPLETED 영상만 다룬다."""

import contextlib
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core import storage
from app.core.errors import AppError
from app.models import Report, Storyboard, Video
from app.models.enums import VideoStage
from app.schemas.library import SortOrder
from app.services import accident_type as accident_type_service

# 영상 하나에 딸린 파일은 S3에서 "{폴더}/{videoId}/..." 아래에 둔다 (삭제할 때 폴더째 지움)
VIDEO_FILE_FOLDERS = ("reports", "storyboards", "videos")


def _library_query(user_id: int):
    return select(Video).where(Video.created_by == user_id, Video.stage == VideoStage.COMPLETED)


def list_videos(
    db: Session,
    user_id: int,
    keyword: str | None,
    accident_type_id: int | None,
    sort: SortOrder,
) -> tuple[list[Video], int]:
    """검색·필터·정렬한 목록과, 필터와 상관없는 전체 개수"""
    query = _library_query(user_id).options(joinedload(Video.accident_type))
    if accident_type_id is not None:
        query = query.where(Video.accident_type_id == accident_type_id)
    if keyword and keyword.strip():
        # 제목에 포함되면 검색 (대소문자 무시). %, _ 는 글자 그대로 찾도록 이스케이프
        escaped = keyword.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.where(Video.title.ilike(f"%{escaped}%", escape="\\"))

    order = Video.updated_at.asc() if sort == SortOrder.OLDEST else Video.updated_at.desc()
    items = list(db.scalars(query.order_by(order, Video.id)).all())

    total_count = db.scalar(select(func.count()).select_from(_library_query(user_id).subquery()))
    return items, total_count or 0


def get_video(db: Session, user_id: int, video_id: uuid.UUID) -> Video:
    """본인 라이브러리 영상 1개. 없거나 남의 영상이거나 아직 완성 전이면 404"""
    video = db.scalar(
        _library_query(user_id).where(Video.id == video_id).options(joinedload(Video.accident_type))
    )
    if video is None:
        raise AppError(404, "VIDEO_NOT_FOUND", "영상을 찾을 수 없습니다.")
    return video


def update_info(
    db: Session, user_id: int, video_id: uuid.UUID, title: str, accident_type_name: str
) -> Video:
    video = get_video(db, user_id, video_id)
    video.title = title
    video.accident_type = accident_type_service.find_or_create(db, user_id, accident_type_name)
    db.commit()
    db.refresh(video)
    return video


def delete_video(db: Session, user_id: int, video_id: uuid.UUID) -> None:
    """DB에서 지운 뒤 S3 파일을 정리한다.

    DB 행(보고서·작업·추출 항목·스토리보드)은 ON DELETE CASCADE로 같이 지워진다.
    파일 삭제는 DB 삭제 뒤에 하고, 실패해도 삭제 자체는 성공으로 본다
    (파일만 남는 건 괜찮지만, 파일 없는 영상이 목록에 남으면 안 되므로).
    """
    video = get_video(db, user_id, video_id)

    keys = {video.video_key, video.thumbnail_key}
    keys.add(db.scalar(select(Report.file_key).where(Report.video_id == video_id)))
    keys.update(db.scalars(select(Storyboard.image_key).where(Storyboard.video_id == video_id)))
    keys.discard(None)

    db.delete(video)
    db.commit()

    with contextlib.suppress(Exception):
        for key in keys:
            storage.delete(key)
        for folder in VIDEO_FILE_FOLDERS:
            storage.delete_prefix(f"{folder}/{video_id}/")
