import os
from typing import List
from datetime import datetime

from django.contrib.auth import authenticate
from django.core.paginator import Paginator
from django.http import FileResponse
from django.shortcuts import get_object_or_404

from ninja import Router, UploadedFile, File
from ninja.errors import HttpError

from rest_framework.decorators import authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.tokens import RefreshToken

from app import settings
from core.requisition.services.notification_service import logger
from core.user.models import User
from core.user.schema import (
    AuthOutput, AuthInput, ChangePasswordIn,
    UserCreateIn, UserUpdateIn,
    PaginatedUserResponse, UserOut, UserSchema
)

router = Router(tags=["Users"])


# ========== HELPER PARA GRUPOS ==========
def resolve_group_ids(data: dict):
    """
    Aceita tanto group_ids (preferido) como groups (legado).
    Retorna None se nenhum dos dois for enviado.
    """
    if "group_ids" in data and data["group_ids"] is not None:
        return data["group_ids"]
    if "groups" in data and data["groups"] is not None:
        return data["groups"]
    return None


# ========== LOGIN ==========
@router.post("/login", response=AuthOutput, auth=None)
def login(request, data: AuthInput):
    user = authenticate(username=data.username, password=data.password)
    if user is None:
        return 401, {"detail": "Credenciais inválidas"}

    refresh = RefreshToken.for_user(user)
    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
    }


# ========== GET ALL USERS (SEM PAGINAÇÃO) ==========
@router.get("", response=List[UserOut])
def get_users(request):
    users = User.objects.select_related("department", "position")
    return [UserOut.from_orm(user) for user in users]


# ========== PROFILE ==========
@router.get("/profile", response=UserSchema)
def get_user_profile(request):
    user = request.auth
    if not user or not hasattr(user, "email"):
        return {"detail": "Usuário não autenticado"}, 401
    return UserSchema.from_orm(user)


# ========== CHANGE PASSWORD ==========
@router.post("/{user_id}/change-password")
def change_password(request, user_id: int, payload: ChangePasswordIn):
    user = get_object_or_404(User, id=user_id)

    if not user.check_password(payload.old_password):
        return {"success": False, "error": "Senha atual incorreta"}

    user.set_password(payload.new_password)
    user.save()
    return {"success": True, "message": "Senha alterada com sucesso"}


# ========== CREATE USER ==========
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.post("", response=UserOut)
def create_user(request, payload: UserCreateIn):

    user = User.objects.create_user(
        username=payload.username,
        email=payload.email,
        first_name=payload.first_name,
        last_name=payload.last_name,
        password=payload.password,
        department_id=payload.department_id,
        position_id=payload.position_id,
        is_active=payload.is_active,
    )

    # grupos
    group_ids = resolve_group_ids(payload.dict())
    if group_ids:
        user.groups.set(group_ids)

    return UserOut.from_orm(user)


# ========== LIST USERS (PAGINATED) ==========
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.get("/list", response=PaginatedUserResponse)
def get_users_paginated(request, page: int = 1, page_size: int = 15):
    try:
        queryset = (
            User.objects.select_related("department", "position")
            .all()
            .order_by('-id')
        )

        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page)

        items = [UserOut.from_orm(u) for u in page_obj]

        return {
            "count": paginator.count,
            "total_pages": paginator.num_pages,
            "current_page": page_obj.number,
            "page_size": page_size,
            "has_next": page_obj.has_next(),
            "has_prev": page_obj.has_previous(),
            "items": items,
        }

    except Exception as e:
        logger.error(f"Erro no endpoint users: {str(e)}")
        raise HttpError(500, "Erro interno do servidor")


# ========== GET ONE USER ==========
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.get("/{user_id}", response=UserOut)
def get_user_by_id(request, user_id: int):
    user = get_object_or_404(
        User.objects.select_related("department", "position"),
        id=user_id
    )
    return UserOut.from_orm(user)


# ========== UPDATE USER ==========
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.post("/{user_id}", response=UserOut)
def update_user(request, user_id: int, payload: UserUpdateIn):
    user = get_object_or_404(User, id=user_id)

    data = payload.dict(exclude_unset=True)

    # atualizar password apenas se enviada
    if "password" in data and data["password"]:
        user.set_password(data.pop("password"))

    # outros campos
    for attr in [
        "username", "email", "first_name", "last_name",
        "is_active", "department_id", "position_id"
    ]:
        if attr in data:
            setattr(user, attr, data[attr])

    user.save()

    # atualizar grupos somente se enviados
    group_ids = resolve_group_ids(data)
    if group_ids is not None:
        user.groups.set(group_ids)

    return UserOut.from_orm(user)


# ========== UPDATE USER IMAGE (CORRIGIDO) ==========
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.post("/{user_id}/image", response=UserOut)
def update_user_image(request, user_id: int, image: UploadedFile = File(...)):
    user = get_object_or_404(User, id=user_id)
    user.image.save(image.name, image, save=True)
    return UserOut.from_orm(user)


# ========== ACTIVATE USER ==========
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.patch("/{user_id}/deactivate")
def deactivate_user(request, user_id: int):
    user = get_object_or_404(User, id=user_id)
    user.is_active = False
    user.save()
    return {"success": True}


@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.patch("/{user_id}/activate")
def activate_user(request, user_id: int):
    user = get_object_or_404(User, id=user_id)
    user.is_active = True
    user.save()
    return {"success": True}


# ========== UPLOAD FILE (LEGADO) ==========
# @authentication_classes([JWTAuthentication])
# @permission_classes([IsAuthenticated])
# @router.post("/upload")
# def upload_user_file(request, user_id: int, file: UploadedFile = File(...)):
#     user = get_object_or_404(User, id=user_id)
#
#     folder = datetime.now().strftime("%Y%m%d")
#     upload_dir = os.path.join(settings.MEDIA_ROOT, "users", folder)
#     os.makedirs(upload_dir, exist_ok=True)
#
#     file_path = os.path.join(upload_dir, file.name)
#
#     with open(file_path, "wb+") as destination:
#         for chunk in file.chunks():
#             destination.write(chunk)
#
#     user.image = f"users/{folder}/{file.name}"
#     user.save()
#
#     return {"success": True, "filename": user.image}
#

# ========== DOWNLOAD FILE ==========
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.get("/download/{file_path}")
def download_user_file(request, file_path: str):
    final_path = os.path.join(settings.MEDIA_ROOT, file_path)

    if not os.path.exists(final_path):
        raise HttpError(404, "Arquivo não encontrado")

    return FileResponse(open(final_path, "rb"), as_attachment=True, filename=os.path.basename(file_path))