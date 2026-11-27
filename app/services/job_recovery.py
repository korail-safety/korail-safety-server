"""서버 재시작으로 끊긴 AI 작업 정리.

AI 작업은 서버 프로세스 안의 백그라운드 작업(BackgroundTasks)으로 돈다.
서버가 꺼지면(코드 수정 후 --reload, 배포 등) 작업도 같이 끝나는데,
DB에는 IN_PROGRESS로 남아서 화면은 계속 "진행 중"이고 삭제·다시 시도도 막힌다.
그래서 서버가 켜질 때 남아 있는 IN_PROGRESS 작업을 실패로 바꾼다.

주의: 서버 프로세스를 여러 개(--workers 2 이상) 띄우면, 나중에 켜진 프로세스가
다른 프로세스에서 실제로 돌고 있는 작업까지 실패로 바꾼다. 프로세스 1개 기준.
"""

import logging
from datetime import UTC, datetime

from sqlalchemy import update

from app.core.database import SessionLocal
from app.models import Job
from app.models.enums import JobStatus, JobType

logger = logging.getLogger(__name__)

# 작업 종류별로 화면에 보여줄 실패 코드 (서버 규칙 문서의 errorCode)
INTERRUPTED_ERROR_CODES = {
    JobType.ANALYSIS: "E-102",
    JobType.STORYBOARD: "E-201",
    JobType.GENERATION: "E-301",
}


def fail_interrupted_jobs() -> None:
    db = SessionLocal()
    try:
        total = 0
        for job_type, error_code in INTERRUPTED_ERROR_CODES.items():
            result = db.execute(
                update(Job)
                .where(Job.status == JobStatus.IN_PROGRESS, Job.type == job_type)
                .values(
                    status=JobStatus.FAILED,
                    error_code=error_code,
                    finished_at=datetime.now(UTC),
                )
            )
            total += result.rowcount
        db.commit()
        if total:
            logger.warning("서버 재시작으로 끊긴 AI 작업 %d개를 실패로 처리했습니다.", total)
    except Exception:
        # 정리에 실패해도 서버는 켜져야 한다 (DB가 아직 안 떴을 때 등)
        db.rollback()
        logger.exception("끊긴 AI 작업 정리에 실패했습니다.")
    finally:
        db.close()
