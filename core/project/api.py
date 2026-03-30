from typing import List
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404
from ninja.files import UploadedFile
from ninja import Router, File
from ninja.errors import HttpError, logger
from .models import Project

from ..project.schemas import ProjectIn, ProjectOut, PaginatedProjectResponse
import pandas as pd
from core.login.jwt_auth import JWTAuth


router = Router(tags=["Project"], auth=JWTAuth())

def check_admin(request):
    if not getattr(request.auth, 'is_administrator', False):
        raise HttpError(403, "Apenas administradores podem executar esta ação.")

@router.post("")
def create_project(request, payload: ProjectIn):
    check_admin(request)
    project = Project.objects.create(**payload.dict())

    return {
        "success": True,
        "data": {
            "id": project.id,
            "name": project.name,
            "description": project.description,
            "cod_contractor": project.cod_contractor,
            "cod_supervision": project.cod_supervision,
            "is_active": project.is_active,
            "localization": project.localization,
            "cost_center": project.cost_center,
        }
    }


REQUIRED_COLUMNS = [
    "name",
    "cod_contractor",
    "cod_supervision",
    "cost_center",
    "localization"
]


@router.post("/import-excel")
def import_projects_excel(request, file: UploadedFile = File(...)):
    check_admin(request)
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

            # ✅ Converter "SIM"/"NÃO" para True/False
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

            project = Project.objects.create(
                name=row["name"],
                description=row.get("description", ""),
                cod_contractor=row["cod_contractor"],
                cod_supervision=row["cod_supervision"],
                cost_center=row["cost_center"],
                localization=row["localization"],
                is_active=is_active_value,
            )
            created.append(project.id)

        except Exception as e:
            errors.append(f"Linha {idx + 2}: {str(e)}")
            continue

    return {
        "imported_ids": created,
        "errors": errors,
        "total_imported": len(created),
        "total_errors": len(errors)
    }

@router.get("", response=List[ProjectOut])
def get_all_projects(request, page: int = 1, page_size: int = 10):
    qs = Project.objects.all()
    return qs

@router.get("/list", response=PaginatedProjectResponse)
def get_projects(request, page: int = 1, page_size: int = 100):
    try:
        queryset = (Project.objects.all().order_by('-id'))

        paginator = Paginator(queryset, page_size)
        current_page = paginator.get_page(page)

        result = []
        for project in current_page:
            data = ProjectOut.from_orm(project)
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
        logger.error(f"Erro no endpoint projects: {str(e)}")
        raise HttpError(500, "Erro interno do servidor")



@router.get("/{project_id}", response=ProjectOut)
def get_project_by_id(request, project_id: int):
    project = get_object_or_404(Project, id=project_id)
    return project

@router.patch("/{project_id}/deactivate")
def deactivate_project(request, project_id: int):
    check_admin(request)
    project = get_object_or_404(Project, id=project_id)
    project.is_active = False
    project.save()
    return {"success": True}

@router.patch("/{project_id}/activate")
def activate_project(request, project_id: int):
    check_admin(request)
    project = get_object_or_404(Project, id=project_id)
    project.is_active = True
    project.save()
    return {"success": True}


@router.put("/{project_id}")
def update_project(request, project_id: int, payload: ProjectIn):
    check_admin(request)
    project = get_object_or_404(Project, id=project_id)
    data = payload.dict()
    
    for attr, value in data.items():
        setattr(project, attr, value)

    project.save()
    return {"success": True}

@router.delete("/{project_id}")
def delete_project(request, project_id: int):
    check_admin(request)
    project = get_object_or_404(Project, id=project_id)
    project.delete()
    return {"success": True}





