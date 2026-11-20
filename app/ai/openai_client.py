from functools import lru_cache

from openai import OpenAI

from app.core.config import settings


@lru_cache
def get_openai_client() -> OpenAI:
    """OpenAI 클라이언트는 매 요청마다 새로 만들 필요 없어서 한 번만 만들어 재사용한다."""
    return OpenAI(api_key=settings.openai_api_key)