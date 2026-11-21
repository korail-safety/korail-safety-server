from pydantic import BaseModel


class AnalyzeStartResponse(BaseModel):
    job_id: int
    status: str


class AnalyzeStatusResponse(BaseModel):
    status: str
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