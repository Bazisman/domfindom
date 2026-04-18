from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, status

from backend.schemas.categories import (
    CategoryCreateRequest,
    CategoryResponse,
    CategoryUpdateRequest,
)
from backend.schemas.common import MessageResponse
from backend.services import category_service


router = APIRouter()


def _to_response(category) -> CategoryResponse:
    return CategoryResponse(
        id=category.id or 0,
        name=category.name,
        type=category.type,
        color=category.color,
        icon=category.icon,
        is_active=category.is_active,
    )


@router.get("", response_model=List[CategoryResponse])
def list_categories(
    type: Optional[str] = Query(default=None),
    include_inactive: bool = Query(default=False),
) -> List[CategoryResponse]:
    categories = category_service.get_all_categories(type, include_inactive=include_inactive)
    return [_to_response(category) for category in categories]


@router.get("/{category_id}", response_model=CategoryResponse)
def get_category(category_id: int) -> CategoryResponse:
    category = category_service.get_category_by_id(category_id)
    if not category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Категория не найдена")
    return _to_response(category)


@router.post("", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
def create_category(payload: CategoryCreateRequest) -> CategoryResponse:
    category_id = category_service.add_category(
        name=payload.name,
        category_type=payload.type,
        color=payload.color,
        icon=payload.icon,
    )
    if not category_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Не удалось создать категорию")

    category = category_service.get_category_by_id(category_id)
    if not category:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Категория создана, но не найдена")
    return _to_response(category)


@router.patch("/{category_id}", response_model=CategoryResponse)
def update_category(category_id: int, payload: CategoryUpdateRequest) -> CategoryResponse:
    category = category_service.get_category_by_id(category_id)
    if not category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Категория не найдена")

    updated = category_service.update_category(
        category_id,
        **payload.model_dump(exclude_none=True),
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Не удалось обновить категорию")

    refreshed = category_service.get_category_by_id(category_id)
    if not refreshed:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Категория обновлена, но не найдена")
    return _to_response(refreshed)


@router.delete("/{category_id}", response_model=MessageResponse)
def delete_category(category_id: int) -> MessageResponse:
    category = category_service.get_category_by_id(category_id)
    if not category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Категория не найдена")

    deleted = category_service.delete_category(category_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Не удалось удалить категорию")
    return MessageResponse(message="Категория отключена")
