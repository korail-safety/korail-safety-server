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


# OpenAI Structured Outputs용 JSON 스키마 — extracted_items.field_key 4종류에 맞춤
EXTRACTED_FIELDS_SCHEMA = {
    "type": "object",
    "properties": {
        "accident_overview": {"type": "string", "description": "사고 개요"},
        "accident_cause": {"type": "string", "description": "사고 원인"},
        "action_taken": {"type": "string", "description": "조치 사항"},
        "prevention": {"type": "string", "description": "재발 방지 대책"},
    },
    "required": ["accident_overview", "accident_cause", "action_taken", "prevention"],
    "additionalProperties": False,
}
