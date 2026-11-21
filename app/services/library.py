"""라이브러리(완성 영상) 조회·수정·삭제. 본인이 만든 COMPLETED 영상만 다룬다."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core.errors import AppError
from app.models import Video
from app.models.enums import VideoStage
from app.schemas.library import SortOrder
from app.services import accident_type as accident_type_service
from app.services.video_files import delete_video_and_files


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
    video = get_video(db, user_id, video_id)
    delete_video_and_files(db, video)
