from datetime import datetime

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """응답 필드를 camelCase로 내보내기 위한 공통 베이스."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class AnalyzeStartResponse(CamelModel):
    job_id: int
    status: str


class AnalyzeStatusResponse(CamelModel):  # GET/videos/{video_id}/analysis에서 응답받을 때
    status: str
    step: str | None = None
    error_code: str | None = None


class ExtractedItemResponse(CamelModel):
    field_key: str
    content: str
    ai_content: str
    source_page: int | None = None
    source_text: str | None = None
    edited_at: datetime | None = None


class AnalysisResultResponse(CamelModel):
    # 보고서 전체 페이지 수 (원문 뷰어 페이지 이동용)
    total_pages: int
    items: list[ExtractedItemResponse]


class ReportPageResponse(CamelModel):
    page_no: int
    text: str


class UpdateItemRequest(BaseModel):  # 요청 바디라 camelCase 불필요
    content: str


# OpenAI Structured Outputs용 JSON 스키마 — extracted_items.field_key 4종류에 맞춤
def _field_schema(description: str) -> dict:
    return {
        "type": "object",
        "description": description,
        "properties": {
            "content": {"type": "string"},
            "source_page": {
                "type": ["integer", "null"],
                "description": "근거 페이지 번호(1부터 시작), 없으면 null",
            },
            "source_text": {
                "type": ["string", "null"],
                "description": "근거가 되는 원문 일부, 없으면 null",
            },
        },
        "required": ["content", "source_page", "source_text"],
        "additionalProperties": False,
    }


EXTRACTED_FIELDS_SCHEMA = {
    "type": "object",
    "properties": {
        "accident_overview": _field_schema("사고 개요"),
        "accident_cause": _field_schema("사고 원인"),
        "action_taken": _field_schema("조치 사항"),
        "prevention": _field_schema("재발 방지 대책"),
    },
    "required": ["accident_overview", "accident_cause", "action_taken", "prevention"],
    "additionalProperties": False,
}
