from ninja import Router
from typing import List, Optional
from django.contrib.auth.models import Permission
from rest_framework.decorators import authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication

from .schemas import GroupIn, GroupOut, PermissionSchema, PaginatedGroupResponse
from . import services

router = Router(tags=["Access Control"])

# -------------------------
# LISTAR TODAS AS PERMISSIONS
# -------------------------
@router.get("/permissions", response=List[PermissionSchema])
def get_permissions(request):
    return Permission.objects.all()


# -------------------------
# LISTAR GRUPOS
# -------------------------
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.get("/groups", response=PaginatedGroupResponse)
def groups_list(
    request,
    page: int = 1,
    page_size: int = 15,
    search: Optional[str] = None
):
    qs = services.search_groups(search)
    return services.paginate(qs, page, page_size)


# -------------------------
# CRIAR GRUPO
# -------------------------
@router.post("/groups", response=GroupOut)
def group_create(request, data: GroupIn):
    group = services.create_group(data)
    return services.get_group(group.id)


# -------------------------
# VER UM GRUPO
# -------------------------
@router.get("/groups/{group_id}", response=GroupOut)
def group_detail(request, group_id: int):
    return services.get_group(group_id)


# -------------------------
# EDITAR GRUPO
# -------------------------
@router.put("/groups/{group_id}", response=GroupOut)
def group_update(request, group_id: int, data: GroupIn):
    services.update_group(group_id, data)
    return services.get_group(group_id)


# -------------------------
# APAGAR GRUPO
# -------------------------
@router.delete("/groups/{group_id}")
def group_delete(request, group_id: int):
    services.delete_group(group_id)
    return {"success": True}