import base64
import json
import re
import unicodedata
from datetime import UTC, datetime
from io import BytesIO

import pypdfium2 as pdfium
from rapidfuzz import fuzz
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


# 근거 문장 위치 찾기 기준
# AI는 PDF를 자기 방식으로 읽어서 원문과 글자가 조금씩 다르게 준다 (㎞→km, 따옴표·괄호 생략 등).
# 그래서 완전히 같은 문장이 아니라 "충분히 비슷한 구간"을 찾는다.
_MIN_MATCH_SCORE = 85  # 비슷한 정도(0~100). 이 이상이면 같은 문장으로 본다
_MIN_FUZZY_LENGTH = 10  # 이보다 짧은 문장은 엉뚱한 곳이 잡힐 수 있어서 완전히 같을 때만


def _normalize_with_map(text: str) -> tuple[str, list[int]]:
    """비교용으로 글자를 정리하고, 정리한 글자마다 원래 몇 번째 글자였는지 기억한다.

    - 유니코드 정규화(NFKC): ㎞→km, ⑮→15 처럼 모양만 다른 글자를 같게
    - 띄어쓰기·줄바꿈·따옴표·괄호 같은 문장부호는 뺀다
    """
    chars: list[str] = []
    index_map: list[int] = []
    for index, char in enumerate(text):
        for normalized in unicodedata.normalize("NFKC", char):
            if normalized.isalnum():
                chars.append(normalized.lower())
                index_map.append(index)
    return "".join(chars), index_map


def _find_source_rects(page: "pdfium.PdfPage", source_text: str) -> list[dict] | None:
    """페이지 안에서 source_text와 가장 비슷한 구간을 찾아 좌표(0~1 비율, 왼쪽 위 원점)로 변환한다.
    못 찾으면 None (프론트에서 "AI가 참고한 문장"으로 대체 표시)."""
    if not source_text:
        return None

    try:
        textpage = page.get_textpage()
        char_count = textpage.count_chars()
        page_text = textpage.get_text_range(0, char_count)
        # 글자 위치(index)로 좌표를 구하므로, 뽑은 글자 수와 페이지 글자 수가 같아야 한다
        if len(page_text) != char_count:
            return None

        haystack, haystack_map = _normalize_with_map(page_text)
        needle, _ = _normalize_with_map(source_text)
        if not needle or not haystack:
            return None

        if len(needle) < _MIN_FUZZY_LENGTH:
            start = haystack.find(needle)
            if start < 0:
                return None
            end = start + len(needle)
        else:
            alignment = fuzz.partial_ratio_alignment(
                needle, haystack, score_cutoff=_MIN_MATCH_SCORE
            )
            if alignment is None:
                return None
            start, end = alignment.dest_start, alignment.dest_end

        # 정리한 글자 위치 → 원래 글자 위치
        first = haystack_map[start]
        last = haystack_map[end - 1]

        width, height = page.get_size()
        rects: list[dict] = []
        for i in range(textpage.count_rects(first, last - first + 1)):
            left, bottom, right, top = textpage.get_rect(i)
            rects.append(
                {
                    "x": left / width,
                    "y": (height - top) / height,
                    "width": (right - left) / width,
                    "height": (top - bottom) / height,
                }
            )
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
                # 파일 업로드한 그대로 저장소에서 읽어옴
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
                response = client.with_options(timeout=180.0, max_retries=1).responses.create(
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
                                        "각 항목은 핵심만 5문장 이내로 "
                                        "간결하게 요약해줘. "
                                        "불필요하게 길게 설명하지 마. "
                                        "만약 깔끔하게 요약하기 어렵다면, "
                                        "그 항목과 관련된 문장을 문서 원문 "
                                        "그대로 한 문장만 복사해서 넣어도 "
                                        "괜찮아. 완전히 빈 문자열은 그 내용과 "
                                        "관련된 문장을 문서에서 전혀 찾을 수 "
                                        "없을 때만 사용해. 내용을 지어내거나 "
                                        "추측하지는 마. "
                                        "각 항목마다 그 내용의 근거가 되는 문장을 "
                                        "sources 배열로 최대 5개까지 알려줘. "
                                        "각 근거는 페이지 번호(source_page, 1부터 "
                                        "시작)와 근거 원문 일부(source_text)로 "
                                        "이루어져. source_text는 문서 원문에서 "
                                        "이어지는 한 구절을 한 글자도 바꾸지 말고 "
                                        "그대로 복사해줘. 절대 요약하거나 줄여 "
                                        "쓰지 말고, '…'이나 '...' 같은 생략 표시도 "
                                        "쓰지 마. 근거를 명확히 찾을 수 없으면 "
                                        "sources는 빈 배열로 둬."
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
                    sources = (item.get("sources") or [])[:5]

                    source_list: list[dict] = []
                    for source in sources:
                        page = source.get("source_page")
                        text = source.get("source_text")
                        if not page or not text or not (1 <= page <= len(pdf)):
                            continue
                        rects = _find_source_rects(pdf[page - 1], text)
                        source_list.append({"page": page, "text": text, "rects": rects})

                    first = source_list[0] if source_list else {}
                    values = {
                        "content": item["content"],
                        "ai_content": item["content"],
                        # 구버전 프론트 호환용 — sources[0] 값
                        "source_page": first.get("page"),
                        "source_text": first.get("text"),
                        "source_rects": source_list or None,
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
            error_code = job.error_code
            db.rollback()
            job.error_code = error_code
            job.status = JobStatus.FAILED
            raise
        finally:
            job.finished_at = datetime.now(UTC)
            db.commit()
    finally:
        db.close()
