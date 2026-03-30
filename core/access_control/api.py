from ninja import Router
from typing import List, Optional
from django.contrib.auth.models import Permission
from ninja.errors import HttpError

from core.login.jwt_auth import JWTAuth
from .schemas import GroupIn, GroupOut, PermissionSchema, PaginatedGroupResponse
from . import services

router = Router(tags=["Access Control"], auth=JWTAuth())

def check_admin(request):
    if not getattr(request.auth, 'is_administrator', False):
        raise HttpError(403, "Apenas administradores podem aceder a este recurso.")

# -------------------------
# LISTAR TODAS AS PERMISSIONS
# -------------------------
@router.get("/permissions", response=List[PermissionSchema])
def get_permissions(request):
    check_admin(request)
    return Permission.objects.all()


# -------------------------
# LISTAR GRUPOS
# -------------------------
@router.get("/groups", response=PaginatedGroupResponse)
def groups_list(
    request,
    page: int = 1,
    page_size: int = 15,
    search: Optional[str] = None
):
    check_admin(request)
    qs = services.search_groups(search)
    return services.paginate(qs, page, page_size)


# -------------------------
# CRIAR GRUPO
# -------------------------
@router.post("/groups", response=GroupOut)
def group_create(request, data: GroupIn):
    check_admin(request)
    group = services.create_group(data)
    return services.get_group(group.id)


# -------------------------
# VER UM GRUPO
# -------------------------
@router.get("/groups/{group_id}", response=GroupOut)
def group_detail(request, group_id: int):
    check_admin(request)
    return services.get_group(group_id)


# -------------------------
# EDITAR GRUPO
# -------------------------
@router.put("/groups/{group_id}", response=GroupOut)
def group_update(request, group_id: int, data: GroupIn):
    check_admin(request)
    services.update_group(group_id, data)
    return services.get_group(group_id)


# -------------------------
# APAGAR GRUPO
# -------------------------
@router.delete("/groups/{group_id}")
def group_delete(request, group_id: int):
    check_admin(request)
    services.delete_group(group_id)
    return {"success": True}