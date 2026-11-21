import uuid

from app.core.database import SessionLocal
from app.models.report import Report
from app.models.video import Video

TEST_USER_ID = 1  # 2단계에서 psql로 확인한 실제 숫자 id로 바꿔주기
TEST_PDF_PATH = r"C:\Users\52340\OneDrive\바탕 화면\내일미래일경험_프로젝트형\탈선보고서_3p.pdf"

db = SessionLocal()
# uuid.uuid4()는 무작위로 새 ID를 생성하는 함수
video = Video(id=uuid.uuid4(), created_by=TEST_USER_ID)
db.add(video)

report = Report(
    video_id=video.id,
    original_file_name="sample1.pdf",
    file_key=TEST_PDF_PATH,
    file_size=0,
    mime_type="application/pdf",
)
db.add(report)
db.commit()

print("video_id:", video.id)
db.close()
