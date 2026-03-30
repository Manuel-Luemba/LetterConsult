from typing import List
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404
from ninja.errors import HttpError, logger
from ninja import Router, UploadedFile, File
import pandas as pd
from core.login.jwt_auth import JWTAuth

from .models import Department
from ..activity.api import REQUIRED_COLUMNS
from ..activity.models import Activity
from ..activity.schemas import ActivityOut, PaginatedActivityResponse, ActivityIn
from ..project.schemas_department import PaginatedDepartmentResponse, DepartmentIn
from ..timesheet.schemas import DepartmentOut

router = Router(tags=["Erp"], auth=JWTAuth())

@router.post("", response={201: dict})
def create_activity(request, payload: ActivityIn):
    activity = Activity.objects.create(
        name=payload.name,
        description=payload.description,
        department_id=payload.department
    )
    return 201, {"id": activity.id}


@router.get("", response=List[DepartmentOut])
def get_all_departments(request):
    qs = Department.objects.all()
    return qs


@router.get("/list", response=PaginatedDepartmentResponse)
def get_departments(request, page: int = 1, page_size: int = 15):
    """
    Endpoint com paginação manual para atividades
    """
    try:
        queryset = (Activity.objects.select_related("department").all().order_by('-id'))

        paginator = Paginator(queryset, page_size)
        current_page = paginator.get_page(page)

        result = []
        for activity in current_page:
            data = ActivityOut.from_orm(activity)
            result.append(data)

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


@router.get("/{department_id}", response=ActivityOut)
def get_department_by_id(request, department_id: int):
    department = get_object_or_404(Activity, id=department_id)
    return department

@router.post("/import-excel")
def import_projects_excel(request, file: UploadedFile = File(...)):
    try:
        df = pd.read_excel(file.file)
    except Exception as e:
        return 400, {"error": f"Erro ao ler o Excel: {str(e)}"}

    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        return 400, {"error": f"Colunas obrigatórias ausentes: {', '.join(missing)}"}

    created = []
    errors = []

    for idx, row in df.iterrows():
        try:
            if pd.isna(row["name"]) or pd.isna(row["cod_contractor"]):
                errors.append(f"Linha {idx + 2}: faltam dados obrigatórios")
                continue

            is_active_value = True
            if "is_active" in df.columns and not pd.isna(row.get("is_active")):
                is_active_str = str(row.get("is_active")).upper().strip()
                if is_active_str in ["SIM", "YES", "TRUE", "1", "S", "Y"]:
                    is_active_value = True
                elif is_active_str in ["NÃO", "NAO", "NO", "FALSE", "0", "N"]:
                    is_active_value = False
                else:
                    errors.append(f"Linha {idx + 2}: valor inválido para is_active")
                    continue

            activity = Activity.objects.create(
                name=row["name"],
                description=row.get("description", ""),
                department=row["department"],
                is_active=is_active_value,
            )
            created.append(activity.id)

        except Exception as e:
            errors.append(f"Linha {idx + 2}: {str(e)}")
            continue

    return {
        "imported_ids": created,
        "errors": errors,
        "total_imported": len(created),
        "total_errors": len(errors)
    }


@router.put("/{department_id}")
def update_department(request, department_id: int, payload: DepartmentIn):
    department = get_object_or_404(Department, id=department_id)
    data = payload.dict()

    if "manager" in data:
        department.manager = data.pop("manager")

    for attr, value in data.items():
        setattr(department, attr, value)

    department.save()
    return {"success": True}


@router.patch("/activities/{activity_id}")
def delete_activity(request, activity_id: int):
    activity = get_object_or_404(Activity, id=activity_id)
    activity.is_active = False
    activity.save()
    return {"success": True}

@router.patch("/{activity_id}/deactivate")
def deactivate_activity(request, activity_id: int):
    activity = get_object_or_404(Activity, id=activity_id)
    activity.is_active = False
    activity.save()
    return {"success": True}

@router.patch("/{activity_id}/activate")
def activate_activity(request, activity_id: int):
    activity = get_object_or_404(Activity, id=activity_id)
    activity.is_active = True
    activity.save()
    return {"success": True}