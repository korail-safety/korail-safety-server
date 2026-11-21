"""영상 작업 삭제 공통 로직 (라이브러리 삭제·임시저장 삭제가 같이 쓴다)."""

import contextlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import storage
from app.models import Report, Storyboard, Video

# 영상 하나에 딸린 파일은 S3에서 "{폴더}/{videoId}/..." 아래에 둔다 (삭제할 때 폴더째 지움)
VIDEO_FILE_FOLDERS = ("reports", "storyboards", "videos")


def delete_video_and_files(db: Session, video: Video) -> None:
    """DB에서 지운 뒤 S3 파일을 정리한다.

    DB 행(보고서·작업·추출 항목·스토리보드)은 ON DELETE CASCADE로 같이 지워진다.
    파일 삭제는 DB 삭제 뒤에 하고, 실패해도 삭제 자체는 성공으로 본다
    (파일만 남는 건 괜찮지만, 파일 없는 영상이 목록에 남으면 안 되므로).
    """
    video_id = video.id
    keys = {video.video_key, video.thumbnail_key}
    keys.add(db.scalar(select(Report.file_key).where(Report.video_id == video_id)))
    keys.update(db.scalars(select(Storyboard.image_key).where(Storyboard.video_id == video_id)))
    keys.discard(None)

    db.delete(video)
    db.commit()

    with contextlib.suppress(Exception):
        for key in keys:
            storage.delete(key)
        for folder in VIDEO_FILE_FOLDERS:
            storage.delete_prefix(f"{folder}/{video_id}/")
