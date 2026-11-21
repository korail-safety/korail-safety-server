"""사고 유형 비즈니스 로직. 사고 유형은 사용자별 목록이라 모든 조회에 user_id 조건을 건다."""

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import AccidentType, Video
from app.models.enums import VideoStage


def _not_found() -> AppError:
    # 남의 유형도 "없는 유형"으로 처리 (존재 여부를 알려주지 않음)
    return AppError(404, "ACCIDENT_TYPE_NOT_FOUND", "사고 유형을 찾을 수 없습니다.")


def _duplicated() -> AppError:
    return AppError(409, "ACCIDENT_TYPE_DUPLICATED", "이미 있는 유형 이름입니다.")


def _get_own(db: Session, user_id: int, type_id: int) -> AccidentType:
    accident_type = db.scalar(
        select(AccidentType).where(AccidentType.id == type_id, AccidentType.user_id == user_id)
    )
    if accident_type is None:
        raise _not_found()
    return accident_type


def _name_exists(db: Session, user_id: int, name: str, exclude_id: int | None = None) -> bool:
    query = select(AccidentType.id).where(
        AccidentType.user_id == user_id, AccidentType.name == name
    )
    if exclude_id is not None:
        query = query.where(AccidentType.id != exclude_id)
    return db.scalar(query) is not None


def list_with_counts(db: Session, user_id: int) -> list[tuple[AccidentType, int]]:
    """본인 유형 전체 + 유형별 라이브러리 영상 수 (영상 0개인 유형도 포함, 만든 순서대로)"""
    video_count = (
        func.count(Video.id).filter(Video.stage == VideoStage.COMPLETED).label("video_count")
    )
    rows = db.execute(
        select(AccidentType, video_count)
        .outerjoin(Video, Video.accident_type_id == AccidentType.id)
        .where(AccidentType.user_id == user_id)
        .group_by(AccidentType.id)
        .order_by(AccidentType.created_at, AccidentType.id)
    ).all()
    return [(row[0], row[1]) for row in rows]


def create(db: Session, user_id: int, name: str) -> AccidentType:
    if _name_exists(db, user_id, name):
        raise _duplicated()
    accident_type = AccidentType(user_id=user_id, name=name)
    db.add(accident_type)
    _commit_or_duplicated(db)
    return accident_type


def rename(db: Session, user_id: int, type_id: int, name: str) -> AccidentType:
    accident_type = _get_own(db, user_id, type_id)
    if _name_exists(db, user_id, name, exclude_id=type_id):
        raise _duplicated()
    accident_type.name = name
    _commit_or_duplicated(db)
    return accident_type


def delete(db: Session, user_id: int, type_id: int) -> None:
    accident_type = _get_own(db, user_id, type_id)
    # 이 유형을 쓰는 영상이 하나라도 있으면 삭제 불가 (DB도 ON DELETE RESTRICT로 막음)
    in_use = db.scalar(select(Video.id).where(Video.accident_type_id == type_id).limit(1))
    if in_use is not None:
        raise AppError(
            409, "ACCIDENT_TYPE_IN_USE", "이 유형을 쓰는 영상이 있어서 삭제할 수 없습니다."
        )
    db.delete(accident_type)
    db.commit()


def find_or_create(db: Session, user_id: int, name: str) -> AccidentType:
    """영상 저장·라이브러리 수정 때 사용: 같은 이름이 있으면 그 유형, 없으면 새로 만든다.

    commit은 하지 않는다 (호출하는 쪽에서 영상 변경과 함께 commit).
    """
    name = name.strip()
    accident_type = db.scalar(
        select(AccidentType).where(AccidentType.user_id == user_id, AccidentType.name == name)
    )
    if accident_type is None:
        accident_type = AccidentType(user_id=user_id, name=name)
        db.add(accident_type)
        db.flush()
    return accident_type


def _commit_or_duplicated(db: Session) -> None:
    """동시에 같은 이름을 저장한 경우 DB UNIQUE(user_id, name)에 걸리면 409로 바꾼다."""
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _duplicated() from exc
