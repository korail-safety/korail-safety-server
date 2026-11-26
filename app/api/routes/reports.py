import uuid

from fastapi import APIRouter, File, Response, UploadFile, status

from app.api.deps import CurrentUser, DbSession
from app.core.config import settings
from app.schemas.report import UploadReportResponse
from app.services import report as report_service

router = APIRouter(prefix="/videos", tags=["reports"])


def _read_limited(file: UploadFile) -> bytes:
    """최대 크기 + 1바이트까지만 읽는다 (너무 큰 파일을 끝까지 읽지 않도록)"""
    max_bytes = settings.max_report_size_mb * 1024 * 1024
    return file.file.read(max_bytes + 1)


@router.post("/reports", response_model=UploadReportResponse, status_code=status.HTTP_201_CREATED)
def upload_report(
    user: CurrentUser, db: DbSession, file: UploadFile = File(...)
) -> UploadReportResponse:
    """보고서 PDF를 올려 새 영상 작업을 만든다 (분석은 아직 시작하지 않음)"""
    pdf = report_service.validate_pdf(file.filename, _read_limited(file))
    video = report_service.upload_report(db, user, pdf)
    return UploadReportResponse(video_id=video.id)


@router.put("/{video_id}/report", response_model=UploadReportResponse)
def replace_report(
    video_id: uuid.UUID, user: CurrentUser, db: DbSession, file: UploadFile = File(...)
) -> UploadReportResponse:
    """분석 시작 전에 파일을 바꾸면, 새 작업을 만들지 않고 같은 작업의 보고서만 교체한다"""
    pdf = report_service.validate_pdf(file.filename, _read_limited(file))
    video = report_service.replace_report(db, user, video_id, pdf)
    return UploadReportResponse(video_id=video.id)


@router.delete("/{video_id}/analysis", status_code=status.HTTP_204_NO_CONTENT)
def cancel_analysis(video_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Response:
    """분석 중단: 분석 중 화면에서 나가면 작업(보고서·분석 결과·파일)을 지운다. 복구 불가"""
    report_service.cancel_analysis(db, user, video_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
