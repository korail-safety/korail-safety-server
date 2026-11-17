from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """요청마다 DB 세션을 하나 열고, 끝나면 닫는다 (FastAPI 의존성)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
