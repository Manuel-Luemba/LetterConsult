from typing import List
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404
from ninja.files import UploadedFile
from ninja import Router, File
from ninja.errors import HttpError, logger
from rest_framework.decorators import permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from .models import Project

from ..project.schemas import ProjectIn, ProjectOut, PaginatedProjectResponse
import pandas as pd



router = Router(tags=["Project"])

@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.post("")
def create_project(request, payload: ProjectIn):
    project = Project.objects.create(**payload.dict())

    # ✅ RETORNA TODOS OS DADOS DO PROJETO CRIADO
    return {
        "success": True,
        "data": {
            "id": project.id,
            "name": project.name,
            "description": project.description,
            "cod_contractor": project.cod_contractor,
            "cod_supervision": project.cod_supervision,
            # 🔥 ADICIONE TODOS OS CAMPOS QUE APARECEM NA SUA TABELA
            "is_active": project.is_active,
            "localization": project.localization,
            "cost_center": project.cost_center,
            # ... todos os outros campos do modelo Project
        }
    }


REQUIRED_COLUMNS = [
    "name",
    "cod_contractor",
    "cod_supervision",
    "cost_center",
    "localization"
]


@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.post("/import-excel11")
def import_projects_excel11(request, file: UploadedFile = File(...)):
    print('start import_projects_excel')
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
        if pd.isna(row["name"]) or pd.isna(row["cod_contractor"]):
            errors.append(f"Linha {idx+2}: faltam dados obrigatórios")
            continue

        project = Project.objects.create(
            name=row["name"],
            description=row.get("description"),
            cod_contractor=row["cod_contractor"],
            cod_supervision=row["cod_supervision"],
            cost_center=row["cost_center"],
            localization=row["localization"],
            is_active=row.get("is_active", True),
        )
        created.append(project.id)

    return {
        "imported_ids": created,
        "errors": errors,
        "total_imported": len(created),
        "total_errors": len(errors),
        "success": True,
    }


@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.post("/import-excel")
def import_projects_excel(request, file: UploadedFile = File(...)):
    print("start import_projects_excel")

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

            project = Project.objects.create(
                name=row["name"],
                description=row.get("description", ""),
                cod_contractor=row["cod_contractor"],
                cod_supervision=row["cod_supervision"],
                cost_center=row["cost_center"],
                localization=row["localization"],
                is_active=is_active_value,  # ✅ Agora é True/False
            )
            created.append(project.id)
            print(f"✅ Projeto criado: {project.name} (ativo: {project.is_active})")

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
@router.get("", response=List[ProjectOut])
def get_projects(request, page: int = 1, page_size: int = 10):
    qs = Project.objects.all()
    return qs

@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.get("/list", response=PaginatedProjectResponse)
def get_projects(request, page: int = 1, page_size: int = 100):
    """
    Endpoint com paginação manual para timesheets do usuário
    """
    try:
        queryset = (Project.objects.all().order_by('-id'))


        # ✅ PAGINAÇÃO MANUAL
        paginator = Paginator(queryset, page_size)
        current_page = paginator.get_page(page)

        result = []
        for project in current_page:
            data = ProjectOut.from_orm(project)
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
        logger.error(f"Erro no endpoint projects: {str(e)}")
        raise HttpError(500, "Erro interno do servidor")



@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.get("/{project_id}", response=ProjectOut)
def get_project_by_id(request, project_id: int):
    project = get_object_or_404(Project, id=project_id)
    return project

@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.patch("/{project_id}/deactivate")
def deactivate_project(request, project_id: int):
    print(project_id, 'deactivate_project')
    project = get_object_or_404(Project, id=project_id)
    print(project, 'project')
    project.is_active = False
    project.save()
    return {"success": True}

@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.patch("/{project_id}/activate")
def activate_project(request, project_id: int):
    print(project_id, 'activate_project')
    project = get_object_or_404(Project, id=project_id)
    print(project, 'project')
    project.is_active = True
    project.save()
    return {"success": True}


@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.put("/{project_id}")
def update_project(request, project_id: int, payload: ProjectIn):
    project = get_object_or_404(Project, id=project_id)
    data = payload.dict()
    print(data, 'data')
    # # trata o campo ForeignKey separadamente
    # if "department" in data:
    #     project.department_id = data.pop("department")

    # atualiza os demais campos
    for attr, value in data.items():
        setattr(project, attr, value)

    project.save()
    return {"success": True}

@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.delete("/{project_id}")
def delete_project(request, project_id: int):
    project = get_object_or_404(Project, id=project_id)
    project.delete()
    return {"success": True}





