"""보고서 업로드·교체. 파일은 S3에, 파일 정보는 reports 테이블에 저장한다."""

import contextlib
import io
import uuid
from dataclasses import dataclass
from pathlib import PurePath

from pypdf import PdfReader
from pypdf.errors import PdfReadError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import storage
from app.core.config import settings
from app.core.errors import AppError
from app.models import Report, User, Video
from app.models.enums import VideoStage
from app.services.video_files import delete_video_and_files

PDF_MIME_TYPE = "application/pdf"


@dataclass
class ValidatedPdf:
    data: bytes
    file_name: str
    page_count: int


def validate_pdf(file_name: str | None, data: bytes) -> ValidatedPdf:
    """PDF인지, 크기·암호를 검사한다. 통과하면 페이지 수까지 돌려준다."""
    max_bytes = settings.max_report_size_mb * 1024 * 1024
    if len(data) > max_bytes:
        raise AppError(
            413, "FILE_TOO_LARGE", f"파일은 {settings.max_report_size_mb}MB까지 올릴 수 있습니다."
        )

    name = PurePath(file_name or "report.pdf").name
    # 확장자만 보지 않고 파일 내용의 시작(PDF 시그니처)까지 확인
    if not name.lower().endswith(".pdf") or not data.startswith(b"%PDF-"):
        raise AppError(400, "UNSUPPORTED_FILE_TYPE", "PDF 파일만 올릴 수 있습니다.")

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise AppError(400, "ENCRYPTED_FILE", "암호가 걸린 파일은 분석할 수 없습니다.")
        page_count = len(reader.pages)
    except PdfReadError as exc:
        # PDF처럼 보이지만 깨진 파일
        raise AppError(400, "UNSUPPORTED_FILE_TYPE", "PDF 파일을 읽을 수 없습니다.") from exc

    return ValidatedPdf(data=data, file_name=name, page_count=page_count)


def _report_key(video_id: uuid.UUID) -> str:
    # 원본 파일명(한글·공백 등)은 DB에만 두고, S3 키는 겹치지 않는 영문 이름으로
    return f"reports/{video_id}/{uuid.uuid4().hex}.pdf"


def upload_report(db: Session, user: User, pdf: ValidatedPdf) -> Video:
    """새 영상 작업을 만들고 보고서를 저장한다 (stage = UPLOADED)."""
    video_id = uuid.uuid4()
    key = _report_key(video_id)
    storage.upload_bytes(key, pdf.data, PDF_MIME_TYPE)

    video = Video(
        id=video_id,
        created_by=user.id,
        stage=VideoStage.UPLOADED,
        # 분석 전에는 파일명(확장자 제외)을 제목으로 쓴다
        title=PurePath(pdf.file_name).stem[:100],
    )
    report = Report(
        video_id=video_id,
        original_file_name=pdf.file_name[:255],
        file_key=key,
        file_size=len(pdf.data),
        mime_type=PDF_MIME_TYPE,
        page_count=pdf.page_count,
    )
    db.add_all([video, report])
    try:
        db.commit()
    except Exception:
        # DB 저장에 실패하면 올려 둔 파일도 지운다
        db.rollback()
        storage.delete(key)
        raise
    return video


def replace_report(db: Session, user: User, video_id: uuid.UUID, pdf: ValidatedPdf) -> Video:
    """분석 시작 전(stage = UPLOADED)에만 같은 작업의 보고서를 새 파일로 바꾼다."""
    video = db.get(Video, video_id)
    if video is None:
        raise AppError(404, "VIDEO_NOT_FOUND", "영상 작업을 찾을 수 없습니다.")
    if video.created_by != user.id:
        raise AppError(403, "FORBIDDEN", "본인 작업만 수정할 수 있습니다.")
    if video.stage != VideoStage.UPLOADED:
        raise AppError(409, "ANALYSIS_ALREADY_STARTED", "분석을 시작한 뒤에는 바꿀 수 없습니다.")

    report = db.scalar(select(Report).where(Report.video_id == video_id))
    old_key = report.file_key if report else None

    new_key = _report_key(video_id)
    storage.upload_bytes(new_key, pdf.data, PDF_MIME_TYPE)

    if report is None:
        report = Report(video_id=video_id)
        db.add(report)
    report.original_file_name = pdf.file_name[:255]
    report.file_key = new_key
    report.file_size = len(pdf.data)
    report.mime_type = PDF_MIME_TYPE
    report.page_count = pdf.page_count
    video.title = PurePath(pdf.file_name).stem[:100]

    try:
        db.commit()
    except Exception:
        db.rollback()
        storage.delete(new_key)
        raise

    # 예전 파일 삭제는 실패해도 업로드 자체는 성공으로 본다
    if old_key:
        with contextlib.suppress(Exception):
            storage.delete(old_key)
    return video


def cancel_analysis(db: Session, user: User, video_id: uuid.UUID) -> None:
    """분석 중 화면에서 "나가기": 분석을 중단하고 작업(보고서·분석 결과·파일)을 지운다.

    분석이 돌고 있어도 지운다. 백그라운드 분석은 작업이 지워진 걸 확인하면 멈춘다
    (run_analysis 쪽 확인 로직 필요). 스토리보드 단계부터는 여기서 지우지 않는다.
    """
    video = db.get(Video, video_id)
    if video is None:
        raise AppError(404, "VIDEO_NOT_FOUND", "영상 작업을 찾을 수 없습니다.")
    if video.created_by != user.id:
        raise AppError(403, "FORBIDDEN", "본인 작업만 수정할 수 있습니다.")
    if video.stage not in (VideoStage.UPLOADED, VideoStage.ANALYSIS):
        raise AppError(409, "INVALID_STAGE", "분석 단계에서만 중단할 수 있습니다.")
    delete_video_and_files(db, video)
