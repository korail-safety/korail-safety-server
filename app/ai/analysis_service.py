import base64
import json
import re
from datetime import UTC, datetime
from io import BytesIO

import pypdfium2 as pdfium
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.ai.openai_client import get_openai_client
from app.ai.schemas import EXTRACTED_FIELDS_SCHEMA
from app.core import storage
from app.core.database import SessionLocal
from app.core.storage import read_bytes
from app.models.enums import ExtractedField, JobStatus
from app.models.extracted_item import ExtractedItem
from app.models.job import Job
from app.models.report import Report, ReportPage

MODEL = "gpt-5.6-luna"

FIELD_KEY_MAP = {
    "accident_overview": ExtractedField.ACCIDENT_OVERVIEW,
    "accident_cause": ExtractedField.ACCIDENT_CAUSE,
    "action_taken": ExtractedField.ACTION_TAKEN,
    "prevention": ExtractedField.PREVENTION,
}

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _clean_text(text: str) -> str:
    return _CONTROL_CHARS.sub("", text)


def _find_source_rects(page: "pdfium.PdfPage", source_text: str) -> list[dict] | None:
    """페이지 안에서 source_text를 찾아 좌표(0~1 비율, 왼쪽 위 원점)로 변환한다.
    못 찾으면 None (프론트에서 텍스트로 대체 표시)."""
    if not source_text:
        return None

    width, height = page.get_size()
    textpage = page.get_textpage()
    rects: list[dict] = []
    try:
        searcher = textpage.search(source_text, match_case=False, match_whole_word=False)
        while True:
            match = searcher.get_next()  # 미검증: 버전에 따라 메서드명이 다를 수 있음
            if match is None:
                break
            index, count = match
            n = textpage.count_rects(index, count)
            for i in range(n):
                left, bottom, right, top = textpage.get_rect(i)
                rects.append(
                    {
                        "x": left / width,
                        "y": (height - top) / height,
                        "width": (right - left) / width,
                        "height": (top - bottom) / height,
                    }
                )
        searcher.close()
    except Exception:
        return None
    return rects or None


def run_analysis(video_id, report_id: int, job_id: int) -> None:
    """백그라운드에서 실행되는 함수라 요청용 DB 세션을 그대로 쓰면 안 되고, 새 세션을 직접 연다."""
    db = SessionLocal()
    try:
        report = db.get(Report, report_id)
        job = db.get(Job, job_id)

        try:
            client = get_openai_client()

            job.step = "READ_FILE"
            db.commit()

            try:
                #파일 업로드한 그대로 저장소에서 읽어옴
                pdf_bytes = read_bytes(report.file_key)
                pdf_base64 = base64.b64encode(pdf_bytes).decode("utf-8")

                pdf = pdfium.PdfDocument(pdf_bytes)
                for i, page in enumerate(pdf):
                    page_no = i + 1
                    textpage = page.get_textpage()
                    text = _clean_text(textpage.get_text_range() or "")

                    bitmap = page.render(scale=2)  # 약 144dpi
                    buf = BytesIO()
                    bitmap.to_pil().save(buf, format="PNG")
                    image_key = f"reports/{video_id}/pages/{page_no}.png"
                    storage.upload_bytes(image_key, buf.getvalue(), "image/png")

                    stmt = pg_insert(ReportPage).values(
                        report_id=report.id,
                        page_no=page_no,
                        text=text,
                        image_key=image_key,
                    )
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["report_id", "page_no"],
                        set_={"text": stmt.excluded.text, "image_key": stmt.excluded.image_key},
                    )
                    db.execute(stmt)
                db.commit()
            except Exception:
                job.error_code = "E-101"
                raise

            job.step = "EXTRACT_KEY_INFO"
            db.commit()

            try:
                response = client.with_options(timeout=180.0).responses.create(
                    model=MODEL,
                    input=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "input_file",
                                    "filename": report.original_file_name,
                                    "file_data": f"data:application/pdf;base64,{pdf_base64}",
                                },
                                {
                                    "type": "input_text",
                                    "text": (
                                        "첨부된 철도 사고 보고서에서 "
                                        "사고 개요, 사고 원인, 조치 사항, "
                                        "재발 방지 대책을 뽑아줘. "
                                        "문서에 명시적으로 없는 내용은 "
                                        "추측하지 말고 빈 문자열로 둬. "
                                        "각 항목은 핵심만 5문장 이내로 "
                                        "간결하게 요약해줘. "
                                        "불필요하게 길게 설명하지 마. "
                                        "각 항목마다 그 내용의 근거가 되는 "
                                        "페이지 번호(source_page, 1부터 시작)와 "
                                        "근거 원문 일부(source_text)도 함께 알려줘. "
                                        "source_text는 문서 원문에서 이어지는 "
                                        "한 구절을 한 글자도 바꾸지 말고 "
                                        "그대로 복사해줘. 절대 요약하거나 "
                                        "줄여 쓰지 말고, '…'이나 '...' 같은 "
                                        "생략 표시도 쓰지 마. 40자를 넘지 않는 "
                                        "짧은 구절로 골라줘. "
                                        "근거를 명확히 특정할 수 없으면 "
                                        "둘 다 null로 둬."
                                    ),
                                },
                            ],
                        }
                    ],
                    text={
                        "format": {
                            "type": "json_schema",
                            "name": "extracted_fields",
                            "schema": EXTRACTED_FIELDS_SCHEMA,
                            "strict": True,
                        }
                    },
                )
                result = json.loads(response.output_text)

                for key, field_enum in FIELD_KEY_MAP.items():
                    item = result[key]
                    source_page = item.get("source_page")
                    source_text = item.get("source_text")
                    source_rects = None
                    if source_page and source_text and 1 <= source_page <= len(pdf):
                        source_rects = _find_source_rects(pdf[source_page - 1], source_text)

                    values = {
                        "content": item["content"],
                        "ai_content": item["content"],
                        "source_page": source_page,
                        "source_text": source_text,
                        "source_rects": source_rects,
                    }
                    stmt = pg_insert(ExtractedItem).values(
                        video_id=video_id, field_key=field_enum, **values
                    )
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["video_id", "field_key"], set_=values
                    )
                    db.execute(stmt)
            except Exception:
                job.error_code = "E-102"
                raise
            finally:
                pdf.close()

            job.status = JobStatus.COMPLETED

        except Exception:
            db.rollback()
            job.status = JobStatus.FAILED
            raise
        finally:
            job.finished_at = datetime.now(UTC)
            db.commit()
    finally:
        db.close()
