from typing import List
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404
from ninja.errors import HttpError, logger
from rest_framework.decorators import permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication

from .models import Activity
from .schemas import ActivityIn, ActivityOut, PaginatedActivityResponse
import pandas as pd
############################### ACTIVIDADES ########################################################
from ninja import Router, UploadedFile, File


router = Router(tags=["Activity"])

@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.post("")
def create_activity(request, payload: ActivityIn):
    activity = Activity.objects.create(
        name=payload.name,
        description=payload.description,
        department_id=payload.department
    )
    return {"id": activity.id}


@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.get("", response=List[ActivityOut])
def get_activities(request):
    qs = Activity.objects.select_related("department").all()
    return qs

@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.get("/list", response=PaginatedActivityResponse)
def get_activities(request, page: int = 1, page_size: int = 15):
    """
    Endpoint com paginação manual para timesheets do usuário
    """
    try:
        queryset = (Activity.objects.select_related("department").all().order_by('-id'))

        # ✅ PAGINAÇÃO MANUAL
        paginator = Paginator(queryset, page_size)
        current_page = paginator.get_page(page)

        result = []
        for activity in current_page:
            data = ActivityOut.from_orm(activity)
            result.append(data)

        # ✅ RETORNO COM METADADOS COMPLETOS
        return {
            'count': paginator.count,
            'total_pages': paginator.num_pages,
            'current_page': current_page.number,
            'page_size': page_size,
            'has_next': current_page.has_next(),
            'has_prev': current_page.has_previous(),
            'items': result
        }

    except Exception as e:
        logger.error(f"Erro no endpoint activities: {str(e)}")
        raise HttpError(500, "Erro interno do servidor")


@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.get("/{activity_id}", response=ActivityOut)
def get_activity_by_id(request, activity_id: int):
    activity = get_object_or_404(Activity, id=activity_id)
    return activity

@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.post("/import-excel")
def import_activities_excel(request, file: UploadedFile = File(...)):
    print("start import_activities_excel")

    try:
        df = pd.read_excel(file.file)
    except Exception as e:
        return {"error": f"Erro ao ler o Excel: {str(e)}"}

    # 1. Validar se todas as colunas obrigatórias existem
    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        return {"error": f"Colunas obrigatórias ausentes: {', '.join(missing)}"}

    created = []
    errors = []

    # 2. Iterar pelas linhas e validar valores
    for idx, row in df.iterrows():
        try:
            if pd.isna(row["name"]) or pd.isna(row["cod_contractor"]):
                errors.append(f"Linha {idx + 2}: faltam dados obrigatórios")
                continue

            # ✅ CORREÇÃO: Converter "SIM"/"NÃO" para True/False
            is_active_value = True  # padrão
            if "is_active" in df.columns and not pd.isna(row.get("is_active")):
                is_active_str = str(row.get("is_active")).upper().strip()
                if is_active_str in ["SIM", "YES", "TRUE", "1", "S", "Y"]:
                    is_active_value = True
                elif is_active_str in ["NÃO", "NAO", "NO", "FALSE", "0", "N"]:
                    is_active_value = False
                else:
                    errors.append(
                        f"Linha {idx + 2}: valor inválido para is_active: '{row.get('is_active')}'. Use SIM ou NÃO")
                    continue

            activity = Activity.objects.create(
                name=row["name"],
                description=row.get("description", ""),
                department=row["department"],
                is_active=is_active_value,  # ✅ Agora é True/False
            )
            created.append(activity.id)
            print(f"✅ Projeto criado: {activity.name} (ativo: {activity.is_active})")

        except Exception as e:
            errors.append(f"Linha {idx + 2}: {str(e)}")
            print(f"❌ Erro na linha {idx + 2}: {str(e)}")
            continue

    return {
        "imported_ids": created,
        "errors": errors,
        "total_imported": len(created),
        "total_errors": len(errors)
    }


@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.put("/{activity_id}")
def update_activity(request, activity_id: int, payload: ActivityIn):
    activity = get_object_or_404(Activity, id=activity_id)
    data = payload.dict()

    # trata o campo ForeignKey separadamente
    if "department" in data:
        activity.department_id = data.pop("department")

    # atualiza os demais campos
    for attr, value in data.items():
        setattr(activity, attr, value)

    activity.save()
    return {"success": True}


@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.patch("/activities/{activity_id}")
def delete_activity(request, activity_id: int):
    activity = get_object_or_404(Activity, id=activity_id)
    activity.active = False
    activity.save()
    return {"success": True}

@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.patch("/{activity_id}/deactivate")
def deactivate_activity(request, activity_id: int):
    print(activity_id, 'deactivate_activity')
    activity = get_object_or_404(Activity, id=activity_id)
    print(activity, 'activity')
    activity.is_active = False
    activity.save()
    return {"success": True}

@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.patch("/{activity_id}/activate")
def activate_activity(request, activity_id: int):
    print(activity_id, 'activate_activity')
    activity = get_object_or_404(Activity, id=activity_id)
    print(activity, 'activity')
    activity.is_active = True
    activity.save()
    return {"success": True}

REQUIRED_COLUMNS = [
    "name",
    "department",
    "description",
    "is_active",
]