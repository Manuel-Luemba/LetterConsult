
import os
from time import timezone
from typing import List, Optional
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Sum, Prefetch
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone

from ninja.errors import HttpError, logger
from pydantic.json import Decimal
from pydantic.schema import defaultdict

from rest_framework.decorators import permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication

from core.user.models import User
from core.timesheet.models import  Task, Timesheet, TimesheetComment
from core.timesheet.schemas import  TimesheetIn, TimesheetOut,DepartmentOut, TaskOut, PaginatedTimesheetResponse, ExportRequest

from .validators import TimesheetValidator, field_error

from ..activity.models import Activity
from ..erp.models import Department


from .schemas import (
    TimesheetViewSchema, CommentCreateSchema, TimesheetActionSchema, CommentSchema
)

from ninja.responses import Response

from datetime import datetime
from django.conf import settings
from reportlab.lib.pagesizes import A4
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate,
    Paragraph, Spacer, Table, TableStyle
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas as pdfcanvas

from ..project.models import Project
from ninja import Router
from datetime import  date



router = Router(tags=["Timesheet"])


################################### TIMESHEET ###########################################

@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.get("/my", response=PaginatedTimesheetResponse)
def my_timesheets(request, page: int = 1, page_size: int = 50, start_date: date = None, end_date: date = None):
    """
    Endpoint com paginação manual para timesheets do usuário
    """
    try:
        from django.contrib.auth import get_user_model
        user = request.auth
        queryset = (Timesheet.objects.filter(
            submitted_by=user
        ).select_related(
            'employee', 'department'
        ).prefetch_related(
            'tasks'
        ).annotate(
            tasks_count=Count('tasks')
        ).order_by('-id'))

        if start_date and end_date:
            if start_date > end_date:
                raise HttpError(400, "A data inicial não pode ser posterior à data final")
            queryset = queryset.filter(created_at__range=[start_date, end_date])

        # ✅ PAGINAÇÃO MANUAL
        paginator = Paginator(queryset, page_size)
        current_page = paginator.get_page(page)

        result = []
        for timesheet in current_page:
            data = TimesheetOut.from_orm(timesheet)
            data.status = timesheet.get_status_display()
            data.can_edit = timesheet.can_edit()
            data.can_add_task = timesheet.can_add_task()
            data.employee_name = f"{timesheet.employee.first_name} {timesheet.employee.last_name}"
            data.submitted_name = f"{timesheet.submitted_name()}"
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
        logger.error(f"Erro no endpoint my_timesheets: {str(e)}")
        raise HttpError(500, "Erro interno do servidor")


@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.get("/department", response=PaginatedTimesheetResponse)
def department_timesheets(request, page: int = 1, page_size: int = 30, start_date: date = None, end_date: date = None):
    """
         Lista timesheets submetidas do departamento do coordenador logado ou de qualquer usuário do grupo Gerente.
         Pode filtrar por colaborador.
         """
    try:

        user = request.auth

        # Verifica se o usuário tem acesso: é chefe OU está no grupo Gerente
        is_gerente = user.groups.filter(name='Manager').exists()
        user_department = getattr(user, 'department', None)

        if not user_department or not is_gerente:
            raise HttpError(403, "Acesso negado. Você precisa ser gerente ou chefe de departamento.")

        queryset = Timesheet.objects.filter(
            department=user_department, status='submetido'
        ).select_related(
            'employee', 'department'
        ).prefetch_related(
            'tasks'
        ).annotate(
            tasks_count=Count('tasks')
        ).order_by('-created_at')

        if start_date and end_date:
            if start_date > end_date:
                raise HttpError(400, "A data inicial não pode ser posterior à data final")
            queryset = queryset.filter(created_at__range=[start_date, end_date])

        # ✅ PAGINAÇÃO MANUAL
        paginator = Paginator(queryset, page_size)
        current_page = paginator.get_page(page)

        result = []
        for timesheet in current_page:
            data = TimesheetOut.from_orm(timesheet)
            data.status = timesheet.get_status_display()
            data.can_edit = timesheet.can_edit()
            data.can_add_task = timesheet.can_add_task()
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
        logger.error(f"Erro no endpoint my_timesheets: {str(e)}")
        raise HttpError(500, "Erro interno do servidor")


@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.get("/all", response=PaginatedTimesheetResponse)
def all_timesheets(request, page: int = 1, page_size: int = 10, employee_id: Optional[int] = None,
                   department_id: Optional[int] = None, start_date: date = None, end_date: date = None,
                   status: Optional[str] = None  # ✅ NOVO PARÂMETRO
                   ):
    """
    Lista TODAS as timesheets do sistema (todos os usuários)
    Pode filtrar por colaborador, departamento e período
    """

    # ✅ TODAS as timesheets do sistema (sem filtrar por usuário)
    queryset = Timesheet.objects.filter(status='submetido').select_related(
        'employee', 'department'
    ).prefetch_related(
        'tasks'
    ).annotate(
        tasks_count=Count('tasks')
    ).order_by('-created_at')

    # Filtros opcionais
    if employee_id:
        queryset = queryset.filter(employee_id=employee_id)

    if department_id:
        queryset = queryset.filter(department_id=department_id)

    if start_date and end_date:
        queryset = queryset.filter(created_at__range=[start_date, end_date])

    if status:
        queryset = queryset.filter(status=status)

    # ✅ PAGINAÇÃO MANUAL
    paginator = Paginator(queryset, page_size)
    current_page = paginator.get_page(page)

    result = []
    for timesheet in current_page:
        data = TimesheetOut(
            id=timesheet.id,
            employee_id=timesheet.employee.id if timesheet.employee else None,
            employee_name=timesheet.employee.get_full_name() if timesheet.employee else "Sem colaborador",
            department_id=timesheet.department.id if timesheet.department else None,
            department_name=timesheet.department.name if timesheet.department else None,
            status=timesheet.get_status_display(),
            obs=timesheet.obs,
            total_hour=float(timesheet.total_hour) if timesheet.total_hour else None,
            created_at=timesheet.created_at,
            updated_at=timesheet.updated_at,
            can_edit=timesheet.can_edit(),
            can_add_task=timesheet.can_add_task(),
            tasks=[
                TaskOut.from_orm(task) for task in timesheet.tasks.all()
            ]
        )
        result.append(data)

    # ✅ RETORNO PADRONIZADO
    return {
        'count': paginator.count,
        'total_pages': paginator.num_pages,
        'current_page': current_page.number,
        'page_size': page_size,
        'has_next': current_page.has_next(),
        'has_prev': current_page.has_previous(),
        'items': result
    }


@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.get("/{id}", response=TimesheetOut)
def get_timesheet_by_id(request, id: int):
    """
    Retorna uma ficha de ponto específica pelo ID
    """
    timesheet = Timesheet.objects.select_related(
        'employee', 'department'
    ).annotate(
        tasks_count=Count('tasks')
    ).filter(id=id).first()

    if not timesheet:
        raise Http404("Ficha de ponto não encontrada")

    data = TimesheetOut.from_orm(timesheet)
    data.status = timesheet.get_status_display()
    data.can_edit = timesheet.can_edit()
    data.can_add_task = timesheet.can_add_task()

    return data

@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.put("/{id}", response={200: TimesheetOut, 400: dict, 207: dict})
def update_timesheet(request, id: int, data: TimesheetIn):
    """Atualiza timesheet com validações completas e controle de tasks"""
    try:
        timesheet = get_object_or_404(Timesheet, id=id)

        # ⚠️ Verificações de permissão e status
        TimesheetValidator.validate_timesheet_status(timesheet)
        TimesheetValidator.validate_user_permission(timesheet, request.auth)

        # Preparar dados
        update_data = data.dict()
        employee_id = update_data.get('employee_id', timesheet.employee_id)

        # Validação centralizada
        validation_level = getattr(data, "validation_level", "strict")
        is_valid, daily_totals, warnings = TimesheetValidator.validate_timesheet_data(
            update_data, id, employee_id
        )

        print(f"✅ Validação passou. force_confirm={getattr(data, 'force_confirm', False)}, warnings={len(warnings)}")

        # 🔴 NOVO: VALIDAÇÃO DE LIMITE DIÁRIO AGREGADO (EXTRA)
        if validation_level == "strict":
            # Verificar se após atualização algum dia excede 16h
            for task_data in data.tasks:
                task_date = task_data.created_at
                total_daily = TimesheetValidator._get_aggregated_daily_total(
                    employee_id,
                    task_date,
                    timesheet.id,
                    Decimal('0.00')  # Já incluído na validação principal
                )

                if total_daily > TimesheetValidator.MAX_HOURS_PER_DAY:
                    raise field_error(
                        "tasks",
                        f"Após atualização, dia {task_date} teria {float(total_daily)}h "
                        f"(limite: {TimesheetValidator.MAX_HOURS_PER_DAY}h)"
                    )

        # 🔴 NOVO: Se houver warnings e não for confirmação forçada
        if validation_level == "strict":
            if warnings and not getattr(data, 'force_confirm', False):
                # Determinar tipo de warning principal
                message = None
                if any("superior às 8h normais" in w for w in warnings):
                    message = "⚠️ Total diário superior às 8h normais. Confirme para prosseguir."
                elif any("excede 8 horas" in w for w in warnings):
                    message = "⚠️ Algumas tarefas excedem 8 horas individuais. Confirme para prosseguir."
                elif any("mínimo recomendado" in w for w in warnings):
                    message = "⚠️ Alguns dias têm menos de 8 horas. Confirme para prosseguir."
                else:
                    message = "⚠️ Existem avisos que exigem confirmação."

                return 207, {
                    "warnings": warnings,
                    "requires_confirmation": True,
                    "daily_totals": {str(k): float(v) for k, v in daily_totals.items()},
                    "message": message,
                    "timesheet_id": id,
                    "validation_summary": {
                        "max_hours_per_day": float(TimesheetValidator.MAX_HOURS_PER_DAY),
                        "max_hours_per_task": float(TimesheetValidator.MAX_HOURS_PER_TASK),
                        "max_retroactive_days": TimesheetValidator.MAX_RETROACTIVE_DAYS
                    }
                }

        with transaction.atomic():
            print("🔧 Iniciando transaction...")

            # 🔐 Restrição de alteração de employee_id
            if getattr(data, 'employee_id', None) and data.employee_id != timesheet.employee_id:
                if not request.user.is_superuser:
                    raise HttpError(403, "Você não tem permissão para alterar o funcionário deste timesheet.")
                timesheet.employee = get_object_or_404(User, id=data.employee_id)
                print(f"🔒 employee_id alterado para {data.employee_id} por admin.")

            # 🏢 Fallback e validação do departamento
            if getattr(data, 'department_id', None) is not None:
                department = get_object_or_404(Department, id=data.department_id)
                timesheet.department = department
            elif hasattr(request.user, "department") and request.user.department:
                print(f"ℹ️ Usando fallback de department do usuário: {request.user.department.id}")
                if not request.user.department.is_active:
                    raise HttpError(400, "Departamento do usuário está inativo.")
                timesheet.department = request.user.department
            else:
                raise HttpError(400, "Departamento não informado e não disponível pelo usuário.")

            # Campos adicionais
            if getattr(data, 'created_at', None) is not None:
                timesheet.created_at = data.created_at
            if getattr(data, 'obs', None) is not None:
                timesheet.obs = data.obs
            if getattr(data, 'status', None) is not None:
                timesheet.status = data.status

            # 🔄 ESTRATÉGIA CORRIGIDA: Manter tasks existentes + processar mudanças
            print(f"🔍 Processando {len(data.tasks)} tasks recebidas...")

            # Obter IDs das tasks atuais para comparação
            current_task_ids = set(Task.objects.filter(timesheet=timesheet).values_list('id', flat=True))
            print(f"🔍 Tasks atuais no banco: {current_task_ids}")

            received_task_ids = set()
            tasks_to_update = []
            tasks_to_create = []

            # Analisar tasks recebidas
            for task_data in data.tasks:
                task_id = getattr(task_data, 'id', None)

                if task_id is not None and task_id > 0:
                    # Task existente - verificar se realmente existe
                    if task_id in current_task_ids:
                        tasks_to_update.append((task_id, task_data))
                        received_task_ids.add(task_id)
                        print(f"📝 Task para atualizar: ID {task_id}")
                    else:
                        # ID fornecido mas não existe - tratar como nova
                        tasks_to_create.append(task_data)
                        print(f"🆕 Task com ID {task_id} não encontrada, criando como nova")
                else:
                    # Nova task - criar
                    tasks_to_create.append(task_data)
                    print(f"🆕 Nova task sem ID para criar")

            # 🗑️ Identificar tasks para deletar (as que estão no banco mas não foram recebidas)
            tasks_to_delete_ids = current_task_ids - received_task_ids
            print(f"🔍 Tasks para deletar (não recebidas): {tasks_to_delete_ids}")

            # Atualizar tasks existentes
            for task_id, task_data in tasks_to_update:
                try:
                    existing_task = Task.objects.get(id=task_id, timesheet=timesheet)
                    # ⚠️ VERIFICAR SE HOUVE MUDANÇAS REAIS ANTES DE ATUALIZAR
                    needs_update = (
                            existing_task.project_id != task_data.project_id or
                            existing_task.activity_id != task_data.activity_id or
                            existing_task.hour != task_data.hour or
                            existing_task.created_at != task_data.created_at
                    )

                    if needs_update:
                        existing_task.project = get_object_or_404(Project, id=task_data.project_id)
                        existing_task.activity = get_object_or_404(Activity, id=task_data.activity_id)
                        existing_task.hour = task_data.hour
                        existing_task.created_at = task_data.created_at
                        existing_task.updated_at = timezone.now()
                        existing_task.save()
                        print(f"🔄 Task atualizada: {task_id}")
                    else:
                        print(f"ℹ️ Task {task_id} sem alterações, mantida")

                except Task.DoesNotExist:
                    print(f"⚠️ Task ID {task_id} não encontrada durante atualização")

            # Criar novas tasks
            for task_data in tasks_to_create:
                new_task = Task.objects.create(
                    timesheet=timesheet,
                    project=get_object_or_404(Project, id=task_data.project_id),
                    activity=get_object_or_404(Activity, id=task_data.activity_id),
                    hour=task_data.hour,
                    created_at=task_data.created_at,
                    updated_at=timezone.now()
                )
                print(f"➕ Nova task criada: {new_task.id}")

            # 🗑️ Excluir tasks que não foram recebidas
            if tasks_to_delete_ids:
                tasks_to_delete = Task.objects.filter(
                    timesheet=timesheet,
                    id__in=tasks_to_delete_ids
                )
                deleted_count = tasks_to_delete.delete()[0]
                print(f"🗑️ Tasks excluídas (não recebidas): {deleted_count}")

            # Processar deleted_task_ids explícitos (se houver)
            deleted_task_ids = getattr(data, 'deleted_task_ids', [])
            if deleted_task_ids is None:
                deleted_task_ids = []

            valid_explicit_deletes = []
            for tid in deleted_task_ids:
                try:
                    tid_int = int(tid)
                    if tid_int > 0 and tid_int in current_task_ids:
                        valid_explicit_deletes.append(tid_int)
                except (ValueError, TypeError):
                    continue

            if valid_explicit_deletes:
                explicit_deletes = Task.objects.filter(
                    timesheet=timesheet,
                    id__in=valid_explicit_deletes
                )
                explicit_deleted_count = explicit_deletes.delete()[0]
                print(f"🗑️ Tasks excluídas explicitamente: {explicit_deleted_count}")

            # ⏱️ Recalcular horas totais
            total_hours = Task.objects.filter(timesheet=timesheet).aggregate(
                total=Sum('hour')
            )['total'] or 0

            timesheet.total_hour = float(total_hours)
            timesheet.updated_at = timezone.now()
            timesheet.save()

        print("✅ Timesheet atualizado com sucesso!")
        return 200, TimesheetOut.from_orm(timesheet)

    except HttpError as e:
        print(f"❌ HttpError: {e}")
        raise e
    except Exception as e:
        print(f"❌ ERRO INTERNO: {str(e)}")
        import traceback
        print(f"❌ Traceback: {traceback.format_exc()}")
        raise HttpError(500, f"Erro interno: {str(e)}")


@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.post("/", response={200: TimesheetOut, 400: dict, 207: dict})
def create_timesheet(request, data: TimesheetIn):
    """Cria timesheet usando o validador centralizado"""
    try:
        # Validar dados básicos
        employee = get_object_or_404(User, id=data.employee_id)
        department = get_object_or_404(Department, id=data.department_id)

        # Verifica o tipo de validação (leve ou rígida)
        validation_level = getattr(data, "validation_level", "strict")

        # Calcular totais provisórios para verificação rápida
        provisional_totals = defaultdict(Decimal)
        for task in data.tasks:
            provisional_totals[task.created_at] += Decimal(str(task.hour))

        # Verificação rápida de limites
        if validation_level == "strict":
            for task_date, hours in provisional_totals.items():
                if hours > TimesheetValidator.MAX_HOURS_PER_DAY:
                    return 400, {
                        "error": f"Total diário excedido",
                        "detail": f"Dia {task_date}: {float(hours)}h > {TimesheetValidator.MAX_HOURS_PER_DAY}h",
                        "field": "tasks"
                    }

        # Usar validador centralizado
        is_valid, daily_totals, warnings = TimesheetValidator.validate_timesheet_data(
            data.dict(), employee_id=data.employee_id
        )

        print(f"✅ Validação passou. force_confirm={data.force_confirm}, warnings={len(warnings)}")

        if validation_level == "strict":
            # Se houver avisos e não for confirmação forçada
            if warnings and not data.force_confirm:
                # Determinar tipo de warning
                if any("superior às 8h normais" in w for w in warnings):
                    message = "⚠️ Total diário superior às 8h normais. Confirme para prosseguir."
                elif any("excede 8 horas" in w for w in warnings):
                    message = "⚠️ Algumas tarefas excedem 8 horas individuais. Confirme para prosseguir."
                elif any("mínimo recomendado" in w for w in warnings):
                    message = "⚠️ Alguns dias têm menos de 8 horas. Confirme para prosseguir."
                else:
                    message = "⚠️ Alerta de horas. Confirme para prosseguir."

                return 207, {
                    "warnings": warnings,
                    "requires_confirmation": True,
                    "daily_totals": {str(k): float(v) for k, v in daily_totals.items()},
                    "message": message,
                    "validation_summary": {
                        "max_hours_per_day": float(TimesheetValidator.MAX_HOURS_PER_DAY),
                        "max_hours_per_task": float(TimesheetValidator.MAX_HOURS_PER_TASK),
                        "max_retroactive_days": TimesheetValidator.MAX_RETROACTIVE_DAYS
                    }
                }

        # ⚠️ ADICIONE LOGS DETALHADOS AQUI PARA DEBUG
        print(f"🔧 Criando timesheet... force_confirm={data.force_confirm}")
        print(f"🔧 Employee: {employee.id}, Department: {department.id}")
        print(f"🔧 Tasks quantidade: {len(data.tasks)}")
        print(f"🔧 Tasks: {data.tasks}")

        # CRIAR TIMESHEET
        with transaction.atomic():
            # print("🔧 Iniciando transaction...")
            timesheet = Timesheet.objects.create(
                employee=employee,
                department=department,
                status=data.status,
                obs=data.obs,
                submitted_by=request.auth,
                submitted_at=date.today()
            )
            # print(f"🔧 Timesheet criado: {timesheet.id}")

            for i, task_data in enumerate(data.tasks):
                # print(f"🔧 Criando task {i + 1}: {task_data}")
                activity = get_object_or_404(Activity, id=task_data.activity_id)
                project = get_object_or_404(Project, id=task_data.project_id)

                task = Task.objects.create(
                    timesheet=timesheet,
                    activity=activity,
                    project=project,
                    hour=task_data.hour,
                    created_at=task_data.created_at
                )
                # print(f"🔧 Task {i + 1} criada: {task.id}")
        #
        # print("✅ Timesheet criado com sucesso!")
        return 200, TimesheetOut.from_orm(timesheet)

    except HttpError as e:
        print(f"❌ HttpError: {e}")
        raise e
    except Exception as e:
        #        ⚠️ LOG COMPLETO DO ERRO
        print(f"❌ ERRO INTERNO: {str(e)}")
        print(f"❌ Tipo do erro: {type(e)}")
        import traceback
        print(f"❌ Traceback: {traceback.format_exc()}")
        raise HttpError(500, f"Erro interno: {str(e)}")


@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.delete("/{id}")
def delete_timesheet(request, id: int):
    """
    Exclui uma timesheet com status 'RASCUNHO' se o usuário tiver permissão.
    """
    try:
        user = request.auth

        # Buscar a timesheet
        timesheet = Timesheet.objects.filter(id=id).select_related('employee').first()

        if not timesheet:
            raise HttpError(404, "Timesheet não encontrada.")

        # Verifica se o usuário tem permissão para excluir
        is_gerente = user.groups.filter(name='GESTOR').exists()
        is_chefe = getattr(user, 'department', None) == timesheet.department

        if not (is_gerente or is_chefe):
            raise HttpError(403, "Você não tem permissão para excluir esta timesheet.")

        # Verifica se o status é RASCUNHO
        if timesheet.status != 'rascunho':
            raise HttpError(400, "Só é possível excluir timesheets com status 'RASCUNHO'.")

        # Excluir
        timesheet.delete()

        return {"detail": "Timesheet excluída com sucesso."}

    except Exception as e:
        logger.error(f"Erro ao excluir timesheet {id}: {str(e)}")
        raise HttpError(500, "Erro interno ao tentar excluir a timesheet.")


###################################################################
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.get("/departments", response=List[DepartmentOut])
def get_activities(request):
    qs = Department.objects.all()
    return qs



@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.get("/departments", response=List[DepartmentOut])
def list_departments(request):
    return Department.objects.all()


#################################### TESTE #########################################

@router.get(
    "/view/{timesheet_id}",
    response={200: TimesheetViewSchema, 403: dict, 404: dict}
)
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def get_timesheet_view(request, timesheet_id: int):
    try:
        timesheet = Timesheet.objects.select_related(
            'employee',
            'department'
        ).prefetch_related(
            'tasks',
            'comments',
            'status_changes'
        ).get(id=timesheet_id)

        if not has_view_permission(request.auth, timesheet):
            return Response({"error": "Permission denied"}, status=403)

        # Gerar dados compatíveis com o schema
        data = build_timesheet_view_data(timesheet)

        # Retornar como Response para garantir compatibilidade com o schema
        return Response(data, status=200)

    except Timesheet.DoesNotExist:
        return Response({"error": "Timesheet not found"}, status=404)


@router.post("/{timesheet_id}/comments", response=CommentSchema)
def add_timesheet_comment(request, timesheet_id: int, comment_data: CommentCreateSchema):
    """
    Add a comment to a timesheet
    """
    try:
        timesheet = Timesheet.objects.get(id=timesheet_id)

        if not has_comment_permission(request.user, timesheet):
            return {"error": "Permission denied"}, 403

        comment = TimesheetComment.objects.create(
            timesheet=timesheet,
            author=request.user,
            content=comment_data.content
        )

        return {
            "id": comment.id,
            "author_name": comment.author.get_full_name() or comment.author.username,
            "content": comment.content,
            "created_at": comment.created_at
        }

    except Timesheet.DoesNotExist:
        return {"error": "Timesheet not found"}, 404


@router.patch("/{timesheet_id}/approve")
def approve_timesheet(request, timesheet_id: int, action_data: TimesheetActionSchema = None):
    """
    Approve a timesheet (manager action)
    """
    return change_timesheet_status(
        request, timesheet_id, "approved", action_data.notes if action_data else None
    )


@router.patch("/{timesheet_id}/reject")
def reject_timesheet(request, timesheet_id: int, action_data: TimesheetActionSchema = None):
    """
    Reject a timesheet (manager action)
    """
    return change_timesheet_status(
        request, timesheet_id, "rejected", action_data.notes if action_data else None
    )


@router.patch("/{timesheet_id}/request-changes")
def request_timesheet_changes(request, timesheet_id: int, action_data: TimesheetActionSchema = None):
    """
    Request changes for a timesheet (manager action)
    """
    return change_timesheet_status(
        request, timesheet_id, "changes_requested", action_data.notes if action_data else None
    )


def has_view_permission(user, timesheet):
    print(user, "init ...")
    try:
        # Superusuário tem acesso total
        if user.is_superuser:
            return True

        # ADMINISTRADOR - acesso total
        if user.groups.filter(name='ADMINISTRADOR').exists():
            return True

        # DIREÇÃO - acesso total
        if user.groups.filter(name='DIREÇÃO').exists():
            return True

        # O proprietário sempre pode ver sua própria timesheet
        if timesheet.user == user:
            return True

        # RH - pode ver todas as timesheets submetidas
        if user.groups.filter(name='RH').exists():
            return getattr(timesheet, 'status', None) == 'submetido'

        # GESTOR - pode ver timesheets do seu departamento
        if user.groups.filter(name='GESTOR').exists():
            user_dept = getattr(user, 'department', None)
            timesheet_user_dept = getattr(timesheet.employee, 'department', None)
            return user_dept and timesheet_user_dept and user_dept == timesheet_user_dept

        return False

    except Exception:
        # Em caso de erro, nega por segurança
        return False


def has_comment_permission(user, timesheet):
    """
    Check if user can comment on timesheet
    """
    # Gerentes podem comentar em timesheets do seu departamento
    if user.is_manager and user.department == timesheet.department:
        return True

    # Admin pode comentar em tudo
    if user.is_superuser:
        return True

    return False


def has_approval_permission(user, timesheet):
    """
    Check if user can approve/reject timesheet
    """
    # Apenas gerentes do mesmo departamento podem aprovar
    if user.is_manager and user.department == timesheet.department:
        return True

    # Admin pode aprovar tudo
    if user.is_superuser:
        return True

    return False


def change_timesheet_status(request, timesheet_id, new_status, notes=None):
    """
    Helper function to change timesheet status
    """
    try:
        timesheet = Timesheet.objects.get(id=timesheet_id)

        if not has_approval_permission(request.user, timesheet):
            return {"error": "Permission denied"}, 403

        # Registrar mudança de status
        timesheet.status_changes.create(
            old_status=timesheet.status,
            new_status=new_status,
            changed_by=request.user,
            notes=notes
        )

        # Atualizar status
        timesheet.status = new_status
        timesheet.save()

        return {"success": True, "message": f"Timesheet {new_status} successfully"}

    except Timesheet.DoesNotExist:
        return {"error": "Timesheet not found"}, 404


def build_timesheet_view_data(timesheet):
    """
    Build complete timesheet view data with analytics
    """
    tasks = timesheet.tasks.select_related('project', 'activity').all()

    # Calcular métricas básicas
    total_hours = sum(task.hour for task in tasks)
    work_days = len(set(task.created_at for task in tasks))
    task_count = tasks.count()
    daily_average = total_hours / work_days if work_days > 0 else 0

    # Analytics - Horas por projeto
    hours_by_project = tasks.values('project__name').annotate(
        total_hours=Sum('hour')
    ).order_by('-total_hours')

    project_colors = {
        'Projeto Alpha': '#3B82F6',
        'Projeto Beta': '#10B981',
        'Projeto Gamma': '#8B5CF6',
        'Projeto Delta': '#F59E0B',
        'Projeto Epsilon': '#EF4444'
    }

    hours_by_project_data = [
        {
            "project": item['project__name'],
            "hours": float(item['total_hours']),
            "color": project_colors.get(item['project__name'], '#6B7280')
        }
        for item in hours_by_project
    ]

    # Analytics - Horas diárias
    daily_hours = tasks.values('created_at').annotate(
        daily_total=Sum('hour')
    ).order_by('created_at')

    daily_hours_data = [
        {
            "date": item['created_at'].strftime('%Y-%m-%d'),
            "hours": float(item['daily_total'])
        }
        for item in daily_hours
    ]

    # Breakdown por projeto
    project_breakdown = [
        {
            "name": item['project__name'],
            "hours": float(item['total_hours']),
            "color": project_colors.get(item['project__name'], '#6B7280')
        }
        for item in hours_by_project
    ]

    # Comentários
    comments = [
        {
            "id": comment.id,
            "author_name": comment.author.get_full_name() or comment.author.username,
            "content": comment.content,
            "created_at": comment.created_at
        }
        for comment in timesheet.comments.all().order_by('-created_at')
    ]

    # Histórico de status
    status_history = [
        {
            "status": change.new_status,
            "changed_at": change.changed_at,
            "changed_by": change.changed_by.get_full_name() or change.changed_by.username,
            "notes": change.notes
        }
        for change in timesheet.status_changes.all().order_by('-created_at')
    ]

    return {
        # Informações básicas
        "id": timesheet.id,
        "employee_name": timesheet.employee.get_full_name() or timesheet.employee.username,
        "department_name": timesheet.department.name,
        "status": timesheet.status,
        # "period": f"{timesheet.start_date} to {timesheet.end_date}",
        "submitted_at": timesheet.submitted_at.strftime('%d-%m-%Y'),

        # Métricas
        "total_hours": float(total_hours),
        "work_days": work_days,
        "task_count": task_count,
        "daily_average": round(daily_average, 2),

        # Conteúdo
        "obs": timesheet.obs,
        "tasks": [
            {
                "id": task.id,
                "created_at": task.created_at.strftime('%Y-%m-%d'),
                "project_name": task.project.name,
                "activity_name": task.activity.name,
                "hour": float(task.hour)
                # "description": task.description
            }
            for task in tasks
        ],

        # Analytics
        "hours_by_project": hours_by_project_data,
        "daily_hours": daily_hours_data,
        "project_breakdown": project_breakdown,

        # Histórico e comentários
        "status_history": status_history,
        "comments": comments,
    }


########################### EXPORT ################################################


@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.get("/{timesheet_id}/export-pdf")
def export_timesheet_pdf(request, timesheet_id: int):
    try:
        timesheet = Timesheet.objects.get(id=timesheet_id)
        if not has_view_permission(request.auth, timesheet):
            return {"error": "Permission denied"}, 403

        # ---------- Marca e contactos ----------
        brand_cfg = getattr(settings, "ENGCONSULT_COLORS", {
            "PRIMARY": "#0A4B78", "ACCENT": "#F68B1F", "TEXT": "#1F2937",
            "MUTED_BG": "#F3F4F6", "GRID": "#E5E7EB"
        })
        BRAND_PRIMARY = colors.HexColor(brand_cfg["PRIMARY"])
        BRAND_ACCENT = colors.HexColor(brand_cfg["ACCENT"])
        BRAND_TEXT = colors.HexColor(brand_cfg["TEXT"])
        BRAND_MUTED = colors.HexColor(brand_cfg["MUTED_BG"])
        BRAND_GRID = colors.HexColor(brand_cfg["GRID"])

        contacts = getattr(settings, "ENGCONSULT_CONTACTS", {
            "PHONE": "+244 9xx xxx xxx",
            "EMAIL": "geral@engconsult-ao.com",
            "WEBSITE": "www.engconsult-ao.com",
            "ADDRESS": "Luanda, Angola",
        })

        # Caminho correto para o logo - ajuste conforme sua estrutura
        logo_path = os.path.join(settings.MEDIA_ROOT, 'logo.png')
        logo_exists = os.path.isfile(logo_path)

        # Se não encontrar na raiz do media, tenta em subpastas
        if not logo_exists:
            logo_path = os.path.join(settings.MEDIA_ROOT, 'logos', 'logo.png')
            logo_exists = os.path.isfile(logo_path)

        # ---------- Buffer e documento ----------
        buffer = io.BytesIO()

        # Margens generosas para header/rodapé
        left, right, top, bottom = 72, 72, 110, 90
        doc = BaseDocTemplate(
            buffer, pagesize=A4,
            leftMargin=left, rightMargin=right,
            topMargin=top, bottomMargin=bottom
        )

        # Área útil (frame) onde o conteúdo entra (exclui header/footer)
        frame = Frame(doc.leftMargin, doc.bottomMargin,
                      doc.width, doc.height, id='normal')

        # ---------- Funções de desenho ----------
        def draw_header(canvas, doc_):
            page_w, page_h = A4

            # Logo - posição ajustada
            if logo_exists:
                try:
                    # Posiciona o logo no canto superior esquerdo
                    canvas.drawImage(
                        logo_path,
                        doc_.leftMargin, page_h - top + 15,  # Ajuste na posição Y
                        width=120,
                        height=40,  # Altura um pouco maior para melhor proporção
                        preserveAspectRatio=True,
                        mask='auto'
                    )
                except Exception as e:
                    # Fallback se houver erro com a imagem
                    canvas.setFillColor(colors.red)
                    canvas.setFont("Helvetica", 8)
                    canvas.drawString(doc_.leftMargin, page_h - top + 25, f"[Logo error: {e}]")

            # Título do documento no header (lado direito)
            canvas.setFillColor(BRAND_PRIMARY)
            canvas.setFont("Helvetica-Bold", 14)
            canvas.drawRightString(page_w - doc_.rightMargin, page_h - top + 30, "TIMESHEET")

            # Linha divisória sob o header
            canvas.setStrokeColor(BRAND_PRIMARY)
            canvas.setLineWidth(1)
            y_line = page_h - top + 10  # Linha mais abaixo
            canvas.line(doc_.leftMargin, y_line, page_w - doc_.rightMargin, y_line)

        class NumberedCanvas(pdfcanvas.Canvas):
            def __init__(self, *args, brand_primary=None, brand_text=None, contacts=None, **kwargs):
                super().__init__(*args, **kwargs)
                self._saved_page_states = []
                self.brand_primary = brand_primary or colors.HexColor("#0A4B78")
                self.brand_text = brand_text or colors.black
                self.contacts = contacts or {}

            def showPage(self):
                self._saved_page_states.append(dict(self.__dict__))

            #     super().showPage()

            def save(self):
                # Contar páginas
                num_pages = len(self._saved_page_states)
                for state in self._saved_page_states:
                    self.__dict__.update(state)
                    self._draw_footer(num_pages)
                    super().showPage()
                super().save()

            def _draw_footer(self, total_pages):
                page_w, page_h = A4
                left = 72
                right = page_w - 72
                base_y = 40  # Altura do rodapé

                # Linha acima do rodapé
                self.setStrokeColor(self.brand_primary)
                self.setLineWidth(1)
                self.line(left, base_y + 25, right, base_y + 25)

                # Contactos (lado esquerdo)
                self.setFont("Helvetica", 8)
                self.setFillColor(self.brand_text)

                # Formata os contactos em linhas separadas
                phone = self.contacts.get("PHONE", "")
                email = self.contacts.get("EMAIL", "")
                website = self.contacts.get("WEBSITE", "")
                address = self.contacts.get("ADDRESS", "")

                # Desenha cada linha de contacto
                y_offset = base_y + 15
                if phone:
                    self.drawString(left, y_offset, f"Tel: {phone}")
                    y_offset -= 12
                if email:
                    self.drawString(left, y_offset, f"Email: {email}")
                    y_offset -= 12
                if website:
                    self.drawString(left, y_offset, f"Site: {website}")
                    y_offset -= 12
                if address:
                    self.drawString(left, y_offset, f"End: {address}")

                # Página X de Y (lado direito)
                self.setFont("Helvetica-Bold", 9)
                page_label = f"Página {self._pageNumber} de {total_pages}"
                self.drawRightString(right, base_y + 15, page_label)

                # Data de geração
                self.setFont("Helvetica", 8)
                date_label = f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}"
                self.drawRightString(right, base_y + 5, date_label)

        # PageTemplate com header a cada página
        template = PageTemplate(id='with-header', frames=frame, onPage=draw_header)
        doc.addPageTemplates([template])

        # ---------- Estilos ----------
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'Title',
            parent=styles['Heading1'],
            fontSize=16,
            textColor=BRAND_TEXT,
            spaceAfter=24,
            alignment=1  # Centralizado
        )

        h2_style = ParagraphStyle(
            'H2',
            parent=styles['Heading2'],
            textColor=BRAND_PRIMARY,
            spaceBefore=16,
            spaceAfter=8,
            fontSize=12
        )

        # ---------- Conteúdo ----------
        story = []

        # Título principal (centralizado)
        story.append(Paragraph("RELATÓRIO DE TIMESHEET", title_style))
        story.append(Spacer(1, 10))

        # Informações do colaborador
        employee_info = Paragraph(
            f"<b>Colaborador:</b> {timesheet.employee.get_full_name()}",
            styles['Normal']
        )
        story.append(employee_info)

        # Tabela de informações
        total_horas = sum(t.hour for t in timesheet.tasks.all())
        info_data = [
            ['Departamento:', timesheet.department.name],
            ['Status:', timesheet.status.upper()],
            ['Total de Horas:', f"{total_horas:.1f}h"],
            # ['Período:', f"{timesheet.start_date} a {timesheet.end_date}"],
            ['Submetido em:', timesheet.submitted_at.strftime('%d/%m/%Y %H:%M')]
        ]

        info_tbl = Table(info_data, colWidths=[1.5 * inch, 4.3 * inch])
        info_tbl.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BACKGROUND', (0, 0), (0, -1), BRAND_MUTED),
            ('TEXTCOLOR', (0, 0), (-1, -1), BRAND_TEXT),
            ('GRID', (0, 0), (-1, -1), 1, BRAND_GRID),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('PADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(info_tbl)
        story.append(Spacer(1, 20))

        # Tarefas
        story.append(Paragraph("Tarefas Realizadas", h2_style))
        tasks = timesheet.tasks.select_related('project', 'activity').all()

        if tasks.exists():
            # Cabeçalho da tabela
            data = [['Data', 'Projeto', 'Atividade', 'Horas']]

            # Dados das tarefas
            for task in tasks:
                data.append([
                    task.created_at.strftime('%d/%m/%Y'),
                    task.project.name,
                    task.activity.name,
                    f"{task.hour:.1f}h"
                ])

            # Criar tabela
            tbl = Table(
                data,
                colWidths=[0.9 * inch, 2.5 * inch, 2.0 * inch, 0.6 * inch],
                repeatRows=1  # Repete cabeçalho em todas as páginas
            )

            tbl.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('BACKGROUND', (0, 0), (-1, 0), BRAND_PRIMARY),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('GRID', (0, 0), (-1, -1), 1, BRAND_GRID),
                ('ALIGN', (3, 1), (3, -1), 'CENTER'),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, BRAND_MUTED]),
                ('PADDING', (0, 0), (-1, -1), 4),
            ]))
            story.append(tbl)
        else:
            story.append(Paragraph("Nenhuma tarefa registrada.", styles['Normal']))

        # Observações
        if getattr(timesheet, 'obs', None) and timesheet.obs.strip():
            story.append(Spacer(1, 20))
            story.append(Paragraph("Observações", h2_style))
            story.append(Paragraph(timesheet.obs, styles['Normal']))

        # ---------- Build com canvas numerado ----------
        doc.build(
            story,
            canvasmaker=lambda *a, **kw: NumberedCanvas(
                *a, **kw,
                brand_primary=BRAND_PRIMARY,
                brand_text=BRAND_TEXT,
                contacts=contacts
            )
        )

        # ---------- Resposta HTTP ----------
        buffer.seek(0)
        response = HttpResponse(buffer.getvalue(), content_type='application/pdf')

        # Nome do arquivo
        safe_name = timesheet.employee.get_full_name().replace(' ', '_')
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"timesheet_{safe_name}_{ts}.pdf"

        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response['Pragma'] = 'no-cache'

        return response

    except Timesheet.DoesNotExist:
        return {"error": "Timesheet not found"}, 404
    except Exception as e:
        print("Erro ao gerar PDF:", str(e))
        import traceback
        traceback.print_exc()
        return {"error": "Erro interno ao gerar PDF"}, 500


@router.get("/{timesheet_id}/export-excel")
def export_timesheet_excel(request, timesheet_id: int):
    """
    Export timesheet to Excel
    """
    try:
        timesheet = Timesheet.objects.get(id=timesheet_id)

        if not has_view_permission(request.auth, timesheet):
            return {"error": "Permission denied"}, 403

        # Criar Excel com pandas
        output = io.BytesIO()

        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # Sheet de informações básicas
            info_data = {
                'Campo': ['Funcionário', 'Departamento', 'Status', 'Total de Horas', 'Submetido em'],
                'Valor': [
                    timesheet.employee.get_full_name(),
                    timesheet.department.name,
                    # f"{timesheet.start_date} a {timesheet.end_date}",
                    timesheet.status.upper(),
                    f"{sum(task.hour for task in timesheet.tasks.all()):.1f}h",
                    timesheet.created_at.strftime('%d/%m/%Y %H:%M')
                ]
            }
            info_df = pd.DataFrame(info_data)
            info_df.to_excel(writer, sheet_name='Informações', index=False)

            # Sheet de tarefas
            tasks = timesheet.tasks.select_related('project', 'activity').all()
            tasks_data = []

            for task in tasks:
                tasks_data.append({
                    'Data': task.created_at.strftime('%d/%m/%Y'),
                    'Projeto': task.project.name,
                    'Atividade': task.activity.name,
                    'Horas': task.hour,
                    # 'Descrição': task.description or ''
                })

            if tasks_data:
                tasks_df = pd.DataFrame(tasks_data)
                tasks_df.to_excel(writer, sheet_name='Tarefas', index=False)

            # Sheet de resumo por projeto
            project_hours = {}
            for task in tasks:
                project_name = task.project.name
                project_hours[project_name] = project_hours.get(project_name, 0) + task.hour

            if project_hours:
                summary_data = {
                    'Projeto': list(project_hours.keys()),
                    'Total Horas': list(project_hours.values())
                }
                summary_df = pd.DataFrame(summary_data)
                summary_df.to_excel(writer, sheet_name='Resumo por Projeto', index=False)

        # Retornar arquivo
        output.seek(0)
        response = HttpResponse(
            output.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        file_name = f"timesheet_{timesheet.employee.get_full_name().replace(' ', '_')}_{timesheet.created_at}_{timesheet.id}.xlsx"
        response['Content-Disposition'] = f'attachment; filename="{file_name}"'

        return response

    except Timesheet.DoesNotExist:
        return {"error": "Timesheet not found"}, 404
    except Exception as e:
        print(f"Erro ao gerar Excel: {str(e)}")
        return {"error": "Erro interno ao gerar Excel"}, 500





# @authentication_classes([JWTAuthentication])
# @permission_classes([IsAuthenticated])
# @api.get("timesheets/export", response={200: bytes, 400: dict})
# def export_timesheets(
#     request,
#     timesheet_ids: str,
#     format: str
# ):
#     ids = [int(x) for x in timesheet_ids.split(",")]
#     print(ids)
#     print(timesheet_ids, 'ids recebidos')
#     timesheets = Timesheet.objects.filter(id__in=ids) \
#         .select_related('employee', 'department') \
#         .prefetch_related('tasks__project', 'tasks__activity') \
#         .all()
#
#     """
#     Export timesheets to Excel, CSV or PDF
#     """
#     try:
#         # Usa filter() para múltiplos IDs
#         timesheets = Timesheet.objects.filter(id__in=timesheet_ids)
#
#         # Valida se encontrou algum timesheet
#         if not timesheets.exists():
#             return api.create_response(
#                 request,
#                 {"error": "Nenhum timesheet encontrado"},
#                 status=404
#             )
#
#         print(f"Exportando {timesheets.count()} timesheets")
#
#         # Gera o arquivo baseado no formato
#         if format == "excel":
#             return export_to_excel(timesheets)
#         elif format == "csv":
#             return export_to_csv(timesheets)
#         elif format == "pdf":
#             return export_to_pdf(timesheets)
#
#     except Exception as e:
#         print(f"Erro ao exportar: {e}")
#         return api.create_response(
#             request,
#             {"error": "Erro ao exportar timesheets"},
#             status=500
#         )

# Mostre seu endpoint que retorna o user



################################################################################
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.post("timesheetsw33-export123")
def export_timesheets12(request, payload: ExportRequest):  # ✅ Recebe o schema
    timesheet_ids = payload.timesheet_ids
    format = payload.format

    print(timesheet_ids, "IDs recebidos")
    print(format, "Formato recebido")

    return {"ids": timesheet_ids, "format": format}


from django.http import HttpResponse

import pandas as pd
import io



# @authentication_classes([JWTAuthentication])
# @permission_classes([IsAuthenticated])
# @api.post("timesheets-export")
# def export_timesheets(request, payload: ExportRequest):
#     timesheet_ids = payload.timesheet_ids
#     format = payload.format
#
#     print(f"Exportando {len(timesheet_ids)} timesheets como {format}")
#
#     # Buscar timesheets com todos os relacionamentos
#     timesheets = Timesheet.objects.filter(id__in=timesheet_ids) \
#         .select_related('employee', 'department') \
#         .prefetch_related(
#         Prefetch('tasks', queryset=Task.objects.select_related('project', 'activity'))
#     ) \
#         .prefetch_related('tasks__project', 'tasks__activity').all()
#     print(timesheets, "IDs recebidos")
#
#     if format == "excel":
#         pass
#         #return generate_excel_export(timesheets)
#     elif format == "csv":
#         pass
#       # return generate_csv_export(timesheets)
#     elif format == "pdf":
#         pass
#        # return generate_pdf_export(timesheets)
#
#
# def generate_excel_export(timesheets):
#     # Criar DataFrame com os dados
#     data = []
#     for ts in timesheets:
#         data.append({
#             'ID': ts.id,
#             'Projeto': ts.project.name,
#             'Horas': ts.hours,
#             'Data': ts.date,
#             # ... outros campos
#         })
#
#     df = pd.DataFrame(data)
#
#     # Criar arquivo Excel em memória
#     output = io.BytesIO()
#     with pd.ExcelWriter(output, engine='openpyxl') as writer:
#         df.to_excel(writer, sheet_name='Timesheets', index=False)
#
#     output.seek(0)
#
#     # Retornar como resposta de arquivo
#     response = HttpResponse(
#         output.getvalue(),
#         content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
#     )
#     response['Content-Disposition'] = 'attachment; filename="timesheets_export.xlsx"'
#     return response



@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.post("timesheets-export")
def export_timesheets(request, payload: ExportRequest):
    timesheet_ids = payload.timesheet_ids
    format = payload.format

    print(f"Exportando {len(timesheet_ids)} timesheets como {format}")

    # Buscar timesheets com todos os relacionamentos
    timesheets = Timesheet.objects.filter(id__in=timesheet_ids) \
        .select_related('employee', 'department') \
        .prefetch_related(
        Prefetch('tasks', queryset=Task.objects.select_related('project', 'activity'))
    ) \
        .prefetch_related('tasks__project', 'tasks__activity')

    if format == "excel":
        return generate_complete_excel_export(timesheets)
    elif format == "csv":
        return generate_complete_csv_export(timesheets)
    elif format == "pdf":
        pass
        #return generate_complete_pdf_export(timesheets)


def generate_complete_excel_export(timesheets):
    # Dados principais dos Timesheets
    timesheet_data = []
    task_data = []

    for ts in timesheets:
        # Dados do Timesheet (conforme TimesheetOut)
        timesheet_data.append({
            'Timesheet ID': ts.id,
            'Employee ID': ts.employee.id,
            'Employee Name': f"{ts.employee.first_name} {ts.employee.last_name}",
            'Department ID': ts.department.id if ts.department else None,
            'Department Name': ts.department.name if ts.department else None,
            'Status': ts.status,
            'Observations': ts.obs or '',
            'Total Hours': ts.total_hour or 0,
            'Created At': ts.created_at,
            'Updated At': ts.updated_at,
            'Submitted At': ts.submitted_at,
            'Year': ts.submitted_at.year,
            'Month': ts.submitted_at.month,
            'Week': ts.submitted_at.isocalendar()[1],
            'Day': ts.submitted_at.day,
            'Submitted By': ts.submitted_by,
            'Tasks Count': ts.tasks.count(),
        })

        # Dados das Tasks (conforme TaskOut)
        for task in ts.tasks.all():
            task_data.append({
                'Timesheet ID': ts.id,
                'Task ID': task.id,
                'Project ID': task.project.id if task.project else None,
                'Project Name': task.project.name if task.project else None,
                'Project Centre Cost': task.project.cost_center if task.project else None,
                'Activity ID': task.activity.id if task.activity else None,
                'Activity Name': task.activity.name if task.activity else None,
                'Hours': task.hour,
                'Task Created At': task.created_at,
                'Year Created': ts.created_at.year,
                'Month Created': ts.created_at.month,
                'Week Created': ts.created_at.isocalendar()[1],
                'Day Created': ts.created_at.day,
                'Task Updated At': task.updated_at,
                'Is_Weekend': task.created_at.weekday() >= 5,
            })

    # Criar arquivo Excel com múltiplas abas
    output = io.BytesIO()

    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # Aba de Timesheets
        if timesheet_data:
            df_timesheets = pd.DataFrame(timesheet_data)
            df_timesheets.to_excel(writer, sheet_name='Timesheets', index=False)

        # Aba de Tasks
        if task_data:
            df_tasks = pd.DataFrame(task_data)
            df_tasks.to_excel(writer, sheet_name='Tasks', index=False)

        # Aba de Resumo
        summary_data = {
            'Metric': ['Total Timesheets', 'Total Tasks', 'Total Hours'],
            'Value': [
                len(timesheet_data),
                len(task_data),
                sum(ts['Total Hours'] for ts in timesheet_data)
            ]
        }
        df_summary = pd.DataFrame(summary_data)
        df_summary.to_excel(writer, sheet_name='Summary', index=False)

    output.seek(0)

    response = HttpResponse(
        output.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="complete_timesheets_export.xlsx"'
    return response


def generate_complete_csv_export(timesheets):
    # Similar ao Excel, mas adaptado para CSV
    timesheet_data = []
    task_data = []

    for ts in timesheets:
        timesheet_data.append({
            'Timesheet ID': ts.id,
            'Employee ID': ts.employee.id,
            'Employee Name': f"{ts.employee.first_name} {ts.employee.last_name}",
            'Department ID': ts.department.id if ts.department else None,
            'Department Name': ts.department.name if ts.department else None,
            'Status': ts.status,
            'Observations': ts.obs or '',
            'Total Hours': ts.total_hour or 0,
            'Created At': ts.created_at,
            'Updated At': ts.updated_at,
            'Submitted At': ts.submitted_at,
            'Submitted By': ts.submitted_by,
            'Tasks Count': ts.tasks.count(),
        })

        for task in ts.tasks.all():
            task_data.append({
                'Timesheet ID': ts.id,
                'Task ID': task.id,
                'Project ID': task.project.id if task.project else None,
                'Project Name': task.project.name if task.project else None,
                'Project Centre Cost': task.project.cost_center if task.project else None,
                'Activity ID': task.activity.id if task.activity else None,
                'Activity Name': task.activity.name if task.activity else None,
                'Hours': task.hour,
                'Task Created At': task.created_at,
                'Task Updated At': task.updated_at,
            })

    # Para CSV, você pode retornar os timesheets ou tasks
    # Ou criar um arquivo ZIP com ambos
    df_timesheets = pd.DataFrame(timesheet_data)
    csv_output = df_timesheets.to_csv(index=False)

    response = HttpResponse(csv_output, content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="timesheets_export.csv"'
    return response


# core/timesheet/api.py (ADICIONAR)


@router.post("/timesheets/validate", response={200: dict, 400: dict})
def validate_timesheet_preview(request, data: TimesheetIn):
    """
    Valida uma timesheet SEM criá-la
    Útil para frontend mostrar preview com validações
    """
    try:
        employee = get_object_or_404(User, id=data.employee_id)

        # Executar validação completa
        is_valid, daily_totals, warnings = TimesheetValidator.validate_timesheet_data(
            data.dict(), employee_id=data.employee_id
        )

        # Calcular totais agregados
        aggregated_totals = {}
        for task_date, new_hours in daily_totals.items():
            total_daily = TimesheetValidator._get_aggregated_daily_total(
                data.employee_id,
                task_date,
                None,  # Não excluir nenhuma timesheet
                new_hours
            )
            aggregated_totals[str(task_date)] = float(total_daily)

        return {
            "is_valid": is_valid,
            "warnings": warnings,
            "daily_totals": {str(k): float(v) for k, v in daily_totals.items()},
            "aggregated_totals": aggregated_totals,
            "limits": {
                "max_hours_per_day": float(TimesheetValidator.MAX_HOURS_PER_DAY),
                "max_hours_per_task": float(TimesheetValidator.MAX_HOURS_PER_TASK),
                "max_retroactive_days": TimesheetValidator.MAX_RETROACTIVE_DAYS,
                "min_hours_per_task": float(TimesheetValidator.MIN_HOURS_PER_DAY)
            },
            "summary": {
                "total_days": len(daily_totals),
                "total_hours": sum(float(v) for v in daily_totals.values()),
                "employee_name": employee.get_full_name(),
                "department": employee.department.name if employee.department else None
            }
        }

    except HttpError as e:
        raise e
    except Exception as e:
        raise HttpError(500, f"Erro na validação: {str(e)}")