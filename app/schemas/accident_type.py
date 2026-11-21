from typing import Annotated

from pydantic import StringConstraints, field_serializer

from app.schemas.base import CamelModel

# 앞뒤 공백을 지운 뒤 1~30자 (DB accident_types.name VARCHAR(30))
AccidentTypeName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30)
]


class AccidentTypeRequest(CamelModel):
    """사고 유형 추가·수정 요청 { name }"""

    name: AccidentTypeName


class AccidentTypeResponse(CamelModel):
    """사고 유형 { id, name }. 프론트는 id를 문자열로 다룬다."""

    id: int
    name: str

    @field_serializer("id")
    def serialize_id(self, value: int) -> str:
        return str(value)


class AccidentTypeWithCount(AccidentTypeResponse):
    """목록용. videoCount = 이 유형으로 라이브러리에 저장된 영상 수"""

    video_count: int


class AccidentTypeListResponse(CamelModel):
    items: list[AccidentTypeWithCount]
