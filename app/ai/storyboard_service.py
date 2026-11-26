import io
import json
import base64
from datetime import UTC, datetime
from sqlalchemy import select
from app.core.config import settings
from concurrent.futures import ThreadPoolExecutor
from app.ai.openai_client import get_openai_client
from app.ai.storyboard_schemas import SCENE_BREAKDOWN_SCHEMA
from app.core import storage
from app.core.database import SessionLocal
from app.models.enums import ExtractedField, JobStatus, JobType
from app.models.extracted_item import ExtractedItem
from app.models.job import Job
from app.models.storyboard import Storyboard

IMAGE_QUALITY = "low" if settings.app_env != "production" else "auto"
CHARACTER_SHEET_PREFIX = "assets/characters/"
TEXT_MODEL = "gpt-5.6-luna"  # analysis_service.py의 MODEL과 동일
IMAGE_MODEL = "gpt-image-2.6-flare"
SAFETY_GUIDELINES = (
    "This image is for an official workplace safety-training video for a Korean "
    "public railway corporation. Depict people in professional, fully clothed "
    "work attire (uniforms, safety vests) only. Do not include any sexual, "
    "suggestive, revealing clothing, nudity, or exaggerated body emphasis. "
    "Style must be a clean, professional safety-training illustration suitable "
    "for all audiences, including minors."
)

STYLE_GUIDELINES = (
    "Render in a clean 3D animated/rendered illustration style, like a modern "
    "3D animated short film. Do not use photorealistic or live-action photography style."
)

def get_or_create_character_sheet(client, key: str, description: str) -> str:
    """해당 역할의 캐릭터시트가 저장소에 있으면 그대로 쓰고, 없으면 새로 생성해서 저장한다."""
    s3_key = f"{CHARACTER_SHEET_PREFIX}{key}.png"
    try:
        storage.read_bytes(s3_key)
        return s3_key
    except Exception:
        pass

    character_prompt = (
        "A character reference sheet for an animated safety-training video. "
        "Show the same character in three views on a plain neutral background: "
        "full-body front view, full-body back view, and a close-up face portrait. "
        f"Character: {description}\n\n{STYLE_GUIDELINES}\n\n{SAFETY_GUIDELINES}"
    )
    result = client.images.generate(model=IMAGE_MODEL, prompt=character_prompt, quality=IMAGE_QUALITY)
    image_bytes = base64.b64decode(result.data[0].b64_json)
    storage.upload_bytes(s3_key, image_bytes, "image/png")
    return s3_key

def generate_storyboard(video_id, job_id: int) -> None:
    """장면 구성(시나리오) 생성 + 장면별 Storyboard/Job 행 생성.
    실제 이미지 생성은 장면마다 regenerate_scene_image로 위임한다."""
    db = SessionLocal()
    scene_refs: list[tuple[int, int, int, list[str]]] = []  # (scene_index, storyboard_id, job_id)
    try:
        job = db.get(Job, job_id)
        try:
            client = get_openai_client()

            items = db.scalars(
                select(ExtractedItem).where(ExtractedItem.video_id == video_id)
            ).all()
            content_by_field = {item.field_key: item.content for item in items}
            prompt_text = (
                f"사고 개요: {content_by_field.get(ExtractedField.ACCIDENT_OVERVIEW, '')}\n"
                f"사고 원인: {content_by_field.get(ExtractedField.ACCIDENT_CAUSE, '')}\n"
                f"조치 사항: {content_by_field.get(ExtractedField.ACTION_TAKEN, '')}\n"
                f"재발 방지 대책: {content_by_field.get(ExtractedField.PREVENTION, '')}"
            )

            try:
                response = client.with_options(timeout=180.0, max_retries=1).responses.create(
                    model=TEXT_MODEL,
                    input=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "input_text",
                                    "text": (
                                        "아래 철도 사고 분석 내용을 바탕으로, 직원 대상 안전교육 "
                                        "숏폼 영상의 장면을 나눠줘. 각 장면은 핵심 행동/상황 1개만 "
                                        "보여주고, 8~15개 장면 사이로 구성해줘. 각 장면마다 "
                                        "나레이션/자막용 설명(description, 한국어)과 이미지 생성 AI에 "
                                        "넘길 프롬프트(image_prompt, 영어, 구체적인 인물·행동·배경 "
                                        "묘사)를 함께 줘. image_prompt는 항상 전문적이고 단정한 "
                                        "복장의 안전교육용 일러스트여야 하며, 선정적이거나 신체를 "
                                        "강조하는 묘사는 절대 포함하지 마. 실사(사진) 스타일이 아니라 "
                                        "3D 애니메이션 렌더링 스타일로 묘사해줘. "
                                        "description과 image_prompt 모두에서 실제 인물 이름, 역·노선명, "
                                        "열차 번호, 날짜 등 사건을 특정할 수 있는 정보는 절대 포함하지 말고, "
                                        "'기관사', '역무원', '관제사', '한 철도역', '사고 당일'처럼 "
                                        "일반화한 표현으로 바꿔서 작성해줘.\n\n" + prompt_text
                                    ),
                                }
                            ],
                        }
                    ],
                    text={
                        "format": {
                            "type": "json_schema",
                            "name": "scene_breakdown",
                            "schema": SCENE_BREAKDOWN_SCHEMA,
                            "strict": True,
                        }
                    },
                )
                scenes = json.loads(response.output_text)["scenes"]
                characters = json.loads(response.output_text)["characters"]
            except Exception:
                job.error_code = "E-201"
                raise

            if not scenes:
                job.error_code = "E-201"
                raise RuntimeError("생성된 장면이 없습니다.")
            
            try:
                character_sheet_keys: dict[str, str] = {}
                for character in characters:
                    character_sheet_keys[character["key"]] = get_or_create_character_sheet(
                        client, character["key"], character["description"]
                    )
            except Exception:
                job.error_code = "E-201"
                raise
                
            for i, scene in enumerate(scenes, start=1):
                storyboard = Storyboard(
                    video_id=video_id,
                    scene_index=i,
                    revision=1,
                    prompt=scene["image_prompt"],
                    description=scene["description"],
                )
                db.add(storyboard)
                scene_job = Job(
                    video_id=video_id, type=JobType.STORYBOARD, scene_index=i,
                    status=JobStatus.IN_PROGRESS,
                )
                db.add(scene_job)
                db.flush()  # storyboard.id / scene_job.id 확보
                scene_character_keys = [
                    character_sheet_keys[key] for key in scene["characters"] if key in character_sheet_keys
                ]
                scene_refs.append((i, storyboard.id, scene_job.id, scene_character_keys))

            db.commit()
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

    # 장면 구성 성공 후, 장면별 이미지 생성은 동시에 처리
    # (순차 처리 시 장면 수만큼 오래 걸림 — 13개면 7~8분, 병렬이면 1~2분대로 단축)
    with ThreadPoolExecutor(max_workers=4) as executor:
        for scene_index, storyboard_id, scene_job_id, character_keys in scene_refs:
            executor.submit(
                regenerate_scene_image, video_id, scene_index, storyboard_id, scene_job_id, None, character_keys
            )

def regenerate_scene_image(
        video_id, scene_index: int, storyboard_id: int, job_id: int, 
        source_image_key: str | None = None, 
        character_reference_keys: list[str] | None = None) -> None:
    """백그라운드에서 실행되는 함수라 요청용 DB 세션을 그대로 쓰면 안 되고, 새 세션을 직접 연다."""
    db = SessionLocal()
    try:
        storyboard = db.get(Storyboard, storyboard_id)
        job = db.get(Job, job_id)

        try:
            client = get_openai_client()

            try:
                full_prompt = f"{storyboard.prompt}\n\n{STYLE_GUIDELINES}\n\n{SAFETY_GUIDELINES}"
                if source_image_key:
                    # 수정(revision) 요청: 기존 이미지를 편집
                    source_bytes = storage.read_bytes(source_image_key)
                    source_file = io.BytesIO(source_bytes)
                    source_file.name = "source.png"
                    result = client.images.edit(model=IMAGE_MODEL, image=source_file, prompt=full_prompt, quality=IMAGE_QUALITY)
                elif character_reference_keys:
                    # 최초 생성: 등장인물 캐릭터시트를 레퍼런스로 사용
                    image_files = []
                    for ref_key in character_reference_keys:
                        ref_bytes = storage.read_bytes(ref_key)
                        ref_file = io.BytesIO(ref_bytes)
                        ref_file.name = "character.png"
                        image_files.append(ref_file)
                    result = client.images.edit(model=IMAGE_MODEL, image=image_files, prompt=full_prompt, quality=IMAGE_QUALITY)
                else:
                    # 인물이 안 나오는 장면: 텍스트만으로 생성
                    result = client.images.generate(model=IMAGE_MODEL, prompt=full_prompt, quality=IMAGE_QUALITY)

                image_bytes = base64.b64decode(result.data[0].b64_json)
                image_key = f"storyboards/{video_id}/{scene_index}/{storyboard.revision}.png"
                storage.upload_bytes(image_key, image_bytes, "image/png")
                storyboard.image_key = image_key
                db.commit()
            except Exception:
                job.error_code = "E-201"
                raise

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