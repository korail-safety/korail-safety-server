# app/ai/storyboard_schemas.py
from app.ai.schemas import CamelModel

class StoryboardScene(CamelModel):
    index: int
    image_url: str | None = None
    description: str | None = None
    duration_sec: int | None = None
    status: str
    error_code: str | None = None

class StoryboardResponse(CamelModel):
    status: str
    scenes: list[StoryboardScene]
    error_code: str | None = None

class StoryboardRevisionRequest(CamelModel):
    scene_index: int
    prompt: str

# OpenAI Structured Outputs용 JSON 스키마 — 장면 구성(시나리오) 생성용
SCENE_BREAKDOWN_SCHEMA = {
    "type": "object",
    "properties": {
        "characters": {
            "type": "array",
            "description": (
                "이 영상에 등장하는 인물(역할) 목록 — 실제 장면에 쓰이는 역할만 포함. "
                "key는 정해진 목록 중에서만 고르고, description은 그 인물의 외모·복장을 "
                "일관되게 유지하기 위한 레퍼런스 설명(영어)."
            ),
            "items": {
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "enum": ["engineer", "station_master", "controller"],
                    },
                    "description": {"type": "string"},
                },
                "required": ["key", "description"],
                "additionalProperties": False,
            },
        },
        "scenes": {
            "type": "array",
            "description": "안전교육 숏폼 영상에 들어갈 장면 목록. 장면 1개 = 핵심 행동/상황 1개.",
            "items": {
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "이 장면의 나레이션/자막용 설명(한국어, 1~2문장)",
                    },
                    "image_prompt": {
                        "type": "string",
                        "description": "이미지 생성 AI에 넘길 프롬프트(영어, 인물·행동·배경 구체 묘사)",
                    },
                    "characters": {
                        "type": "array",
                        "description": "이 장면에 등장하는 인물의 key 목록(해당하는 것만, 없으면 빈 배열)",
                        "items": {
                            "type": "string",
                            "enum": ["engineer", "station_master", "controller"],
                        },
                    },
                },
                "required": ["description", "image_prompt", "characters"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["characters", "scenes"],
    "additionalProperties": False,
}