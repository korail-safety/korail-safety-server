"""DB에 저장하는 enum 값. 서버 API 명세의 "Enum 값"과 맞춘다.

DB에는 PostgreSQL ENUM 타입 대신 VARCHAR + CHECK로 저장한다 (값 추가·변경이 쉬움).
"""

from enum import StrEnum

from sqlalchemy import Enum


class VideoStage(StrEnum):
    """영상 진행 단계 (videos.stage)"""

    UPLOADED = "UPLOADED"
    ANALYSIS = "ANALYSIS"
    STORYBOARD = "STORYBOARD"
    GENERATION = "GENERATION"
    COMPLETED = "COMPLETED"


class JobType(StrEnum):
    """AI 작업 종류 (jobs.type)"""

    ANALYSIS = "ANALYSIS"
    STORYBOARD = "STORYBOARD"
    GENERATION = "GENERATION"


class JobStatus(StrEnum):
    """AI 작업 상태 (jobs.status)"""

    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ExtractedField(StrEnum):
    """AI 추출 항목 (extracted_items.field_key)"""

    ACCIDENT_OVERVIEW = "ACCIDENT_OVERVIEW"
    ACCIDENT_CAUSE = "ACCIDENT_CAUSE"
    ACTION_TAKEN = "ACTION_TAKEN"
    PREVENTION = "PREVENTION"


def varchar_enum(enum_cls: type[StrEnum], name: str, length: int = 20) -> Enum:
    """StrEnum → VARCHAR(length) + CHECK (값 목록) 컬럼 타입"""
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=length,
        validate_strings=True,
        values_callable=lambda e: [member.value for member in e],
    )
