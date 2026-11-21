from fastapi import APIRouter, Response, status

from app.api.deps import CurrentUser, DbSession
from app.schemas.accident_type import (
    AccidentTypeListResponse,
    AccidentTypeRequest,
    AccidentTypeResponse,
    AccidentTypeWithCount,
)
from app.services import accident_type as accident_type_service

router = APIRouter(prefix="/accident-types", tags=["accident-types"])


@router.get("", response_model=AccidentTypeListResponse)
def list_accident_types(user: CurrentUser, db: DbSession) -> AccidentTypeListResponse:
    """본인 사고 유형 목록 + 유형별 라이브러리 영상 수"""
    rows = accident_type_service.list_with_counts(db, user.id)
    return AccidentTypeListResponse(
        items=[
            AccidentTypeWithCount(id=item.id, name=item.name, video_count=count)
            for item, count in rows
        ]
    )


@router.post("", response_model=AccidentTypeResponse, status_code=status.HTTP_201_CREATED)
def create_accident_type(
    body: AccidentTypeRequest, user: CurrentUser, db: DbSession
) -> AccidentTypeResponse:
    created = accident_type_service.create(db, user.id, body.name)
    return AccidentTypeResponse.model_validate(created)


@router.patch("/{type_id}", response_model=AccidentTypeResponse)
def rename_accident_type(
    type_id: int, body: AccidentTypeRequest, user: CurrentUser, db: DbSession
) -> AccidentTypeResponse:
    updated = accident_type_service.rename(db, user.id, type_id, body.name)
    return AccidentTypeResponse.model_validate(updated)


@router.delete("/{type_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_accident_type(type_id: int, user: CurrentUser, db: DbSession) -> Response:
    accident_type_service.delete(db, user.id, type_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
