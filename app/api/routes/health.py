from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict[str, str]:
    """서버와 DB가 살아 있는지 확인"""
    db.execute(text("SELECT 1"))
    return {"status": "ok"}
