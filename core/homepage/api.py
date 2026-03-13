from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404

from ninja import Router
from ninja.errors import HttpError
from rest_framework.decorators import authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication

from .models import Position
from .schemas import PositionIn, PositionOut, PaginatedPositionResponse

router = Router(tags=["Positions"])


# ------------------------------------------------------------
# CREATE
# ------------------------------------------------------------
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.post("/create", response=PositionOut)
def create_position(request, payload: PositionIn):
    position = Position.objects.create(
        name=payload.name,
        desc=payload.desc
    )
    return PositionOut(id=position.id, name=position.name)


# ------------------------------------------------------------
# LIST PAGINATED
# ------------------------------------------------------------



@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.get("/list", response=PaginatedPositionResponse)
def get_positions_paginated(request, page: int = 1, page_size: int = 15):
    try:
        queryset = Position.objects.all().order_by("-id")

        paginator = Paginator(queryset, page_size)
        current_page = paginator.get_page(page)

        items = [
            PositionOut(id=p.id, name=p.name)
            for p in current_page
        ]

        return {
            "count": paginator.count,
            "total_pages": paginator.num_pages,
            "current_page": current_page.number,
            "page_size": page_size,
            "has_next": current_page.has_next(),
            "has_prev": current_page.has_previous(),
            "items": items,
        }

    except Exception as e:
        raise HttpError(500, "Erro ao carregar posições")


# ------------------------------------------------------------
# GET BY ID
# ------------------------------------------------------------
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.get("/{position_id}", response=PositionOut)
def get_position(request, position_id: int):
    position = get_object_or_404(Position, id=position_id)
    return PositionOut(id=position.id, name=position.name)


# ------------------------------------------------------------
# UPDATE
# ------------------------------------------------------------
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.put("/{position_id}", response=PositionOut)
def update_position(request, position_id: int, payload: PositionIn):
    position = get_object_or_404(Position, id=position_id)

    position.name = payload.name
    position.desc = payload.desc
    position.save()

    return PositionOut(id=position.id, name=position.name)


# ------------------------------------------------------------
# DELETE
# ------------------------------------------------------------
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.delete("/{position_id}")
def delete_position(request, position_id: int):
    position = get_object_or_404(Position, id=position_id)
    position.delete()

    return {"success": True}