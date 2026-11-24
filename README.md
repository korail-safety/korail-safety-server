# korail-safety-server

생성형 AI 기반 철도 안전교육 영상 자동화 서비스 서버 레포지토리

## 기술 스택

- Python 3.12, [uv](https://docs.astral.sh/uv/) (패키지·가상환경 관리)
- FastAPI
- PostgreSQL 16 (로컬은 Docker), SQLAlchemy 2.0, Alembic, psycopg 3
- Ruff (린트·포맷)

## 처음 실행하기

```bash
# 1. 환경변수 파일 만들기
cp .env.example .env

# 2. 패키지 설치 (.venv 자동 생성)
uv sync

# 3. PostgreSQL 실행 (Docker Desktop 실행 중이어야 함)
docker compose up -d

# 4. 테이블 만들기
uv run alembic upgrade head

# 5. 서버 실행 → http://localhost:8080/docs
uv run uvicorn app.main:app --reload --port 8080
```

`http://localhost:8080/health` 가 `{"status":"ok"}` 이면 서버와 DB가 연결된 상태입니다.

## 폴더 구조

```
app/
├── main.py          # FastAPI 앱, CORS, 에러 처리, 라우터 등록
├── core/            # 설정(.env), DB 연결, 공통 에러 { code, message }
├── models/          # DB 테이블 (ERD 기준 8개)
├── schemas/         # 요청·응답 형식 (Pydantic)
├── services/        # 비즈니스 로직
└── api/routes/      # API 엔드포인트 (기능별 파일)
alembic/versions/    # DB 테이블 변경 기록
make/                # Make 시나리오 블루프린트 백업 (예정)
```

## DB 테이블을 바꿀 때

1. `app/models/` 의 모델을 고친다
2. 변경 기록 만들기: `uv run alembic revision --autogenerate -m "변경 내용"`
3. 만들어진 파일을 열어 확인한 뒤 적용: `uv run alembic upgrade head`
4. ERD에도 같이 반영

## 자주 쓰는 명령

| 명령 | 설명 |
|---|---|
| `uv run ruff check --fix .` | 린트 |
| `uv run ruff format .` | 포맷 |
| `uv run alembic downgrade -1` | 마지막 DB 변경 되돌리기 |
| `docker compose down` | PostgreSQL 종료 (데이터 유지) |
| `docker compose down -v` | PostgreSQL 종료 + 데이터 삭제 |


