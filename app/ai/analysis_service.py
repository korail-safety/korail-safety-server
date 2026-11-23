import base64
import json
import re
from datetime import UTC, datetime
from io import BytesIO

from pypdf import PdfReader
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.ai.openai_client import get_openai_client
from app.ai.schemas import EXTRACTED_FIELDS_SCHEMA
from app.core.database import SessionLocal
from app.core.storage import read_bytes  # S3에 업로드한 파일을 읽을 수 있도록 함.
from app.models.enums import ExtractedField, JobStatus
from app.models.extracted_item import ExtractedItem
from app.models.job import Job
from app.models.report import Report, ReportPage  # ReportPage 추가

# 화요일 데드라인 때문에 분기 없이 PDF 전체를 통째로 AI에게 넘긴다.
# (원래 설계했던 텍스트 추출 우선 분기는 추후 구현 노트 문서 참고)
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

            # file_key가 실제로 가리키는 저장소 방식에 맞게 조정
            pdf_bytes = read_bytes(report.file_key)
            pdf_base64 = base64.b64encode(pdf_bytes).decode("utf-8")

            # report_pages 저장 (OpenAI 호출과는 독립적인 작업)
            reader = PdfReader(BytesIO(pdf_bytes))
            for i, page in enumerate(reader.pages):
                stmt = pg_insert(ReportPage).values(
                    report_id=report.id,
                    page_no=i + 1,  # 1부터 시작
                    text=_clean_text(page.extract_text() or ""),
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=["report_id", "page_no"],
                    set_={"text": stmt.excluded.text},
                )
                db.execute(stmt)
            db.commit()

            job.step = "EXTRACT_KEY_INFO"
            db.commit()

            response = client.responses.create(
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
                                    "첨부된 철도 사고 보고서에서 사고 개요, 사고 원인, 조치 사항, "
                                    "재발 방지 대책을 뽑아줘. 문서에 명시적으로 없는 내용은 "
                                    "추측하지 말고 빈 문자열로 둬. 각 항목은 핵심만 2~3문장 이내로 "
                                    "간결하게 요약해줘. 불필요하게 길게 설명하지 마. "
                                    "각 항목마다 그 내용의 근거가 되는 페이지 번호(source_page, "
                                    "1부터 시작)와 근거 원문 일부(source_text)도 함께 알려줘. "
                                    "근거를 명확히 특정할 수 없으면 둘 다 null로 둬."
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
            # OpenaAI 응답 가져온 거 삭제해야 함. 데이터 노출 위험있음.
            # print("=== RAW OUTPUT ===");print(response.output_text)
            result = json.loads(response.output_text)

            for key, field_enum in FIELD_KEY_MAP.items():
                item = result[key]
                values = {
                    "content": item["content"],
                    "ai_content": item["content"],
                    "source_page": item.get("source_page"),
                    "source_text": item.get("source_text"),
                }
                stmt = pg_insert(ExtractedItem).values(
                    video_id=video_id, field_key=field_enum, **values
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=["video_id", "field_key"], set_=values
                )
                db.execute(stmt)

            job.status = JobStatus.COMPLETED

        except Exception:
            job.status = JobStatus.FAILED
            job.error_code = "ANALYSIS_FAILED"
            raise
        finally:  # 실패와 성공과 관련없이 끝나면 알려줘야 할 것
            job.finished_at = datetime.now(UTC)  # app/models/job.py의 finished_at 컬럼
            db.commit()
    finally:
        db.close()
