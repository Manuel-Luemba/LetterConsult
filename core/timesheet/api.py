
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

from core.login.jwt_auth import JWTAuth
from .models import  Task, Timesheet, TimesheetComment
from .schemas import (
    TimesheetIn, TimesheetOut, DepartmentOut, TaskOut, 
    PaginatedTimesheetResponse, ExportRequest,
    TimesheetDashboardStats, TimesheetStatsCommon, TimesheetStatsManager
)

from .validators import TimesheetValidator, field_error
from .services.timesheet_workflow_service import TimesheetWorkflowService

from ..activity.models import Activity
from ..erp.models import Department


from .schemas import (
    TimesheetViewSchema, CommentCreateSchema, TimesheetActionSchema, CommentSchema, TimesheetReviewIn
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



router = Router(tags=["Timesheet"], auth=JWTAuth())


################################### TIMESHEET ###########################################

@router.get("/", response=PaginatedTimesheetResponse)
def list_timesheets(
    request, 
    page: int = 1, 
    page_size: int = 20, 
    role_context: str = 'requester',
    start_date: date = None, 
    end_date: date = None,
    employee_id: Optional[int] = None,
    department_id: Optional[int] = None,
    status: Optional[str] = None,
    search: Optional[str] = None
):
    """
    Endpoint unificado para listagem de timesheets baseado no contexto do utilizador.
    """
    try:
        user = request.auth
        queryset = Timesheet.objects.select_related(
            'employee', 'department'
        ).prefetch_related(
            'tasks', 'tasks__project', 'tasks__activity'
        ).annotate(
            tasks_count=Count('tasks')
        ).order_by('-created_at', '-id')

        # 1. Aplicar lÃ³gica de Contexto (PermissÃµes e Filtros Base)
        if role_context == 'requester':
            queryset = queryset.filter(submitted_by=user)
        
        elif role_context == 'approver':
            user_department = getattr(user, 'department', None)
            if not user_department:
                raise HttpError(403, "Utilizador sem departamento associado.")
            
            if not user_department.can_be_approved_by(user):
                raise HttpError(403, "Sem permissÃ£o de aprovaÃ§Ã£o para este departamento.")
            
            queryset = queryset.filter(department=user_department)
            if not status:
                queryset = queryset.filter(status__in=['submetido', 'aprovado', 'com_sugestoes', 'com_rejeitadas'])

        elif role_context == 'admin':
            if not (user.is_superuser or user.is_administrator or user.is_director or user.groups.filter(name='RH').exists()):
                raise HttpError(403, "Acesso administrativo negado.")
        
        else:
            raise HttpError(400, f"Contexto de papel invÃ¡lido: {role_context}")

        # 2. Aplicar Filtros Adicionais
        if employee_id:
            queryset = queryset.filter(employee_id=employee_id)
        if department_id:
            queryset = queryset.filter(department_id=department_id)
        if status:
            queryset = queryset.filter(status=status)

        if start_date and end_date:
            queryset = queryset.filter(tasks__created_at__range=[start_date, end_date]).distinct()

        if search:
            from django.db.models import Q
            queryset = queryset.filter(
                Q(employee__first_name__icontains=search) | 
                Q(employee__last_name__icontains=search) |
                Q(obs__icontains=search)
            ).distinct()

        paginator = Paginator(queryset, page_size)
        current_page = paginator.get_page(page)

        result = []
        for timesheet in current_page:
            data = TimesheetOut.model_validate(timesheet)
            data.status = timesheet.get_status_display()
            data.can_edit = timesheet.can_edit()
            data.can_add_task = timesheet.can_add_task()
            if timesheet.employee:
                data.employee_name = timesheet.employee.get_full_name()
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

    except HttpError as e:
        raise e
    except Exception as e:
        logger.error(f"Erro no endpoint unificado list_timesheets: {str(e)}")
        raise HttpError(500, f"Erro interno: {str(e)}")

@router.get("/stats", response={200: TimesheetDashboardStats})
def get_timesheet_stats(request):
    """
    Retorna estatÃ­sticas para o mini-dashboard de timesheets.
    """
    user = request.auth
    today = date.today()
    
    total_hours_month = Task.objects.filter(
        timesheet__employee=user,
        created_at__month=today.month,
        created_at__year=today.year
    ).aggregate(total=Sum('hour'))['total'] or 0.0

    status_counts = Timesheet.objects.filter(
        employee=user
    ).values('status').annotate(count=Count('id'))
    
    pending_count = approved_count = rejected_count = 0
    for s in status_counts:
        st = s['status'].lower()
        if st == 'submetido': pending_count = s['count']
        elif st == 'aprovado': approved_count = s['count']
        elif st in ['com_rejeitadas', 'rejeitado']: rejected_count += s['count']

    total_relevant = pending_count + approved_count + rejected_count
    submission_rate = (approved_count / total_relevant * 100) if total_relevant > 0 else 0.0

    common_stats = TimesheetStatsCommon(
        total_hours_month=float(total_hours_month),
        pending_count=pending_count,
        approved_count=approved_count,
        rejected_count=rejected_count,
        submission_rate=submission_rate
    )

    manager_stats = None
    user_department = getattr(user, 'department', None)
    if user_department and user_department.can_be_approved_by(user):
        pending_my_approval = Timesheet.objects.filter(department=user_department, status='submetido').count()
        approved_by_me_count = Timesheet.objects.filter(
            department=user_department, status='aprovado',
            status_changes__new_status='aprovado', status_changes__changed_by=user,
            status_changes__created_at__month=today.month
        ).distinct().count()
        total_hours_approved = Timesheet.objects.filter(department=user_department, status='aprovado').aggregate(total=Sum('total_hour'))['total'] or 0.0

        manager_stats = TimesheetStatsManager(
            pending_my_approval=pending_my_approval,
            approved_by_me_count=approved_by_me_count,
            avg_approval_time=0.0,
            total_hours_approved=float(total_hours_approved)
        )

    return 200, TimesheetDashboardStats(common=common_stats, manager=manager_stats)


@router.get("/my", response=PaginatedTimesheetResponse)
def my_timesheets(request, page: int = 1, page_size: int = 50, start_date: date = None, end_date: date = None):
    """
    Endpoint com paginaÃ§Ã£o manual para timesheets do usuÃ¡rio
    """
    try:
        user = request.auth
        queryset = (Timesheet.objects.filter(
            submitted_by=user
        ).select_related(
            'employee', 'department'
        ).prefetch_related(
            'tasks', 'tasks__project', 'tasks__activity'
        ).annotate(
            tasks_count=Count('tasks')
        ).order_by('-id'))

        if start_date and end_date:
            if start_date > end_date:
                raise HttpError(400, "A data inicial nÃ£o pode ser posterior Ã  data final")
            queryset = queryset.filter(tasks__created_at__range=[start_date, end_date]).distinct()

        paginator = Paginator(queryset, page_size)
        current_page = paginator.get_page(page)

        result = []
        for timesheet in current_page:
            data = TimesheetOut.model_validate(timesheet)
            data.status = timesheet.get_status_display()
            data.can_edit = timesheet.can_edit()
            data.can_add_task = timesheet.can_add_task()
            data.employee_name = timesheet.employee.get_full_name()
            data.submitted_name = timesheet.submitted_name()
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
        logger.error(f"Erro no endpoint my_timesheets: {str(e)}")
        raise HttpError(500, "Erro interno do servidor")

@router.get("/all", response=PaginatedTimesheetResponse)
def all_timesheets(request, page: int = 1, page_size: int = 10, employee_id: Optional[int] = None,
                   department_id: Optional[int] = None, start_date: date = None, end_date: date = None,
                   status: Optional[str] = None
                   ):
    """
    Lista TODAS as timesheets do sistema (todos os usuÃ¡rios)
    """
    queryset = Timesheet.objects.all().select_related(
        'employee', 'department'
    ).prefetch_related(
        'tasks', 'tasks__project', 'tasks__activity'
    ).annotate(
        tasks_count=Count('tasks')
    ).order_by('-created_at')

    if employee_id:
        queryset = queryset.filter(employee_id=employee_id)
    if department_id:
        queryset = queryset.filter(department_id=department_id)
    if start_date and end_date:
        queryset = queryset.filter(tasks__created_at__range=[start_date, end_date]).distinct()
    if status:
        queryset = queryset.filter(status=status)

    paginator = Paginator(queryset, page_size)
    current_page = paginator.get_page(page)

    result = []
    for timesheet in current_page:
        data = TimesheetOut.model_validate(timesheet)
        data.status = timesheet.get_status_display()
        data.can_edit = timesheet.can_edit()
        data.can_add_task = timesheet.can_add_task()
        if timesheet.employee:
            data.employee_name = timesheet.employee.get_full_name()
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

    data = TimesheetOut.model_validate(timesheet)
    data.status = timesheet.get_status_display()
    data.can_edit = timesheet.can_edit()
    data.can_add_task = timesheet.can_add_task()

    return data

@router.put("/{id}", response={200: TimesheetOut, 400: dict, 207: dict})
def update_timesheet(request, id: int, data: TimesheetIn):
    """Atualiza timesheet com validações completas e controle de tasks"""
    try:
        timesheet = get_object_or_404(Timesheet, id=id)

        # ⚠️ Verificações de permissão e status
        TimesheetValidator.validate_timesheet_status(timesheet)
        TimesheetValidator.validate_user_permission(timesheet, request.auth)

        # Preparar dados
        update_data = data.model_dump()
        employee_id = update_data.get('employee_id', timesheet.employee_id)

        # Validação centralizada
        validation_level = getattr(data, "validation_level", "strict")
        is_valid, daily_totals, warnings = TimesheetValidator.validate_timesheet_data(
            update_data, id, employee_id
        )

        # 🔴 NOVO: VALIDAÇÃO DE LIMITE DIÁRIO AGREGADO (EXTRA)
        if validation_level == "strict":
            for task_data in data.tasks:
                task_date = task_data.created_at
                total_daily = TimesheetValidator._get_aggregated_daily_total(
                    employee_id,
                    task_date,
                    timesheet.id,
                    Decimal('0.00')
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
                message = "⚠️ Existem avisos que exigem confirmação."
                if any("superior" in w for w in warnings): message = "⚠️ Total diário superior às 8h normais. Confirme para prosseguir."
                
                return 207, {
                    "warnings": warnings,
                    "requires_confirmation": True,
                    "daily_totals": {str(k): float(v) for k, v in daily_totals.items()},
                    "message": message,
                    "timesheet_id": id
                }

        with transaction.atomic():
            if getattr(data, 'employee_id', None) and data.employee_id != timesheet.employee_id:
                if not request.auth.is_superuser:
                    raise HttpError(403, "Você não tem permissão para alterar o funcionário deste timesheet.")
                timesheet.employee = get_object_or_404(User, id=data.employee_id)

            if getattr(data, 'department_id', None) is not None:
                timesheet.department = get_object_or_404(Department, id=data.department_id)
            elif hasattr(request.auth, "department") and request.auth.department:
                timesheet.department = request.auth.department

            if getattr(data, 'obs', None) is not None: timesheet.obs = data.obs
            if getattr(data, 'status', None) is not None: timesheet.status = data.status

            # Processamento de tasks
            current_task_ids = set(Task.objects.filter(timesheet=timesheet).values_list('id', flat=True))
            received_task_ids = set()
            
            for task_data in data.tasks:
                task_id = getattr(task_data, 'id', None)
                if task_id and task_id in current_task_ids:
                    received_task_ids.add(task_id)
                    existing_task = Task.objects.get(id=task_id, timesheet=timesheet)
                    existing_task.project = get_object_or_404(Project, id=task_data.project_id)
                    existing_task.activity = get_object_or_404(Activity, id=task_data.activity_id)
                    existing_task.hour = task_data.hour
                    existing_task.created_at = task_data.created_at
                    existing_task.save()
                else:
                    Task.objects.create(
                        timesheet=timesheet,
                        project=get_object_or_404(Project, id=task_data.project_id),
                        activity=get_object_or_404(Activity, id=task_data.activity_id),
                        hour=task_data.hour,
                        created_at=task_data.created_at
                    )

            # Deletar tasks não enviadas
            Task.objects.filter(timesheet=timesheet).exclude(id__in=received_task_ids).delete()

            # Recalcular total
            timesheet.total_hour = float(Task.objects.filter(timesheet=timesheet).aggregate(Sum('hour'))['total'] or 0)
            timesheet.save()

        return 200, TimesheetOut.model_validate(timesheet)

    except HttpError as e:
        raise e
    except Exception as e:
        logger.error(f"Erro no endpoint update_timesheet: {str(e)}")
        raise HttpError(500, f"Erro interno: {str(e)}")

@router.post("/", response={200: TimesheetOut, 400: dict, 207: dict})
def create_timesheet(request, data: TimesheetIn):
    """Cria timesheet usando o validador centralizado"""
    try:
        employee = get_object_or_404(User, id=data.employee_id)
        department = get_object_or_404(Department, id=data.department_id)
        validation_level = getattr(data, "validation_level", "strict")

        # Validação
        is_valid, daily_totals, warnings = TimesheetValidator.validate_timesheet_data(
            data.model_dump(), employee_id=data.employee_id
        )

        if validation_level == "strict" and warnings and not data.force_confirm:
            return 207, {
                "warnings": warnings,
                "requires_confirmation": True,
                "daily_totals": {str(k): float(v) for k, v in daily_totals.items()},
                "message": "Alerta de horas. Confirme para prosseguir."
            }

        with transaction.atomic():
            timesheet = Timesheet.objects.create(
                employee=employee,
                department=department,
                status=data.status,
                obs=data.obs,
                submitted_by=request.auth,
                submitted_at=date.today()
            )

            for task_data in data.tasks:
                Task.objects.create(
                    timesheet=timesheet,
                    activity=get_object_or_404(Activity, id=task_data.activity_id),
                    project=get_object_or_404(Project, id=task_data.project_id),
                    hour=task_data.hour,
                    created_at=task_data.created_at
                )
        
        return 200, TimesheetOut.model_validate(timesheet)

    except Exception as e:
        logger.error(f"Erro no endpoint create_timesheet: {str(e)}")
        raise HttpError(500, f"Erro interno: {str(e)}")


@router.delete("/timesheets/{id}")
def delete_timesheet(request, id: int):
    """
    Exclui uma timesheet com status 'RASCUNHO' se o usuÃ¡rio tiver permissÃ£o.
    """
    try:
        user = request.auth

        # Buscar a timesheet
        timesheet = Timesheet.objects.filter(id=id).select_related('employee').first()

        if not timesheet:
            raise HttpError(404, "Timesheet nÃ£o encontrada.")

        # Verifica se o usuÃ¡rio tem permissÃ£o para excluir
        is_gerente = user.groups.filter(name='GESTOR').exists()
        is_chefe = getattr(user, 'department', None) == timesheet.department

        if not (is_gerente or is_chefe):
            raise HttpError(403, "VocÃª nÃ£o tem permissÃ£o para excluir esta timesheet.")

        # Verifica se o status Ã© RASCUNHO
        if timesheet.status != 'rascunho':
            raise HttpError(400, "SÃ³ Ã© possÃ­vel excluir timesheets com status 'RASCUNHO'.")

        # Excluir
        timesheet.delete()

        return {"detail": "Timesheet excluÃ­da com sucesso."}

    except Exception as e:
        logger.error(f"Erro ao excluir timesheet {id}: {str(e)}")
        raise HttpError(500, "Erro interno ao tentar excluir a timesheet.")


@router.get("/departments", response=List[DepartmentOut])
def list_departments(request):
    """
    Lista todos os departamentos ativos.
    """
    return Department.objects.filter(is_active=True)


#################################### TESTE #########################################

@router.get(
    "timesheets/view/{timesheet_id}",
    response={200: TimesheetViewSchema, 403: dict, 404: dict}
)
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

        # Gerar dados compatÃ­veis com o schema
        data = build_timesheet_view_data(timesheet)

        # Retornar como Response para garantir compatibilidade com o schema
        return Response(data, status=200)

    except Timesheet.DoesNotExist:
        return Response({"error": "Timesheet not found"}, status=404)


@router.post("/{timesheet_id}/comments", response=CommentSchema)
def add_timesheet_comment(request, timesheet_id: int, data: CommentCreateSchema):
    """
    Adiciona um comentário à timesheet.
    """
    timesheet = get_object_or_404(Timesheet, id=timesheet_id)
    service = TimesheetWorkflowService(timesheet)
    comment = service.add_comment(request.auth, data.content)
    
    return CommentSchema.model_validate(comment)

@router.post("/{timesheet_id}/approve", response=TimesheetOut)
def approve_timesheet(request, timesheet_id: int, data: TimesheetReviewIn):
    """
    Aprova uma timesheet (total ou parcialmente).
    """
    timesheet = get_object_or_404(Timesheet, id=timesheet_id)
    service = TimesheetWorkflowService(timesheet)
    updated_timesheet = service.approve(
        approver=request.auth,
        comments=data.notes,
        task_reviews=data.tasks
    )
    return TimesheetOut.model_validate(updated_timesheet)

@router.post("/{timesheet_id}/reject", response=TimesheetOut)
def reject_timesheet(request, timesheet_id: int, data: TimesheetReviewIn):
    """
    Rejeita totalmente uma timesheet.
    """
    timesheet = get_object_or_404(Timesheet, id=timesheet_id)
    service = TimesheetWorkflowService(timesheet)
    updated_timesheet = service.reject(
        approver=request.auth,
        reason=data.notes
    )
    return TimesheetOut.model_validate(updated_timesheet)

@router.post("/{timesheet_id}/request-changes", response=TimesheetOut)
def request_timesheet_changes(request, timesheet_id: int, data: TimesheetReviewIn):
    """
    Solicita alterações na timesheet.
    """
    timesheet = get_object_or_404(Timesheet, id=timesheet_id)
    service = TimesheetWorkflowService(timesheet)
    updated_timesheet = service.request_changes(
        approver=request.auth,
        comments=data.notes
    )
    return TimesheetOut.model_validate(updated_timesheet)

@router.post("/{timesheet_id}/submit", response=TimesheetOut)
def submit_timesheet(request, timesheet_id: int):
    """
    Submete a timesheet para aprovação.
    """
    timesheet = get_object_or_404(Timesheet, id=timesheet_id)
    service = TimesheetWorkflowService(timesheet)
    updated_timesheet = service.submit_for_approval(submitted_by=request.auth)
    return TimesheetOut.model_validate(updated_timesheet)


def has_view_permission(user, timesheet):
    print(user, "init ...")
    try:
        # SuperusuÃ¡rio tem acesso total
        if user.is_superuser:
            return True

        # ADMINISTRADOR - acesso total
        if user.groups.filter(name='ADMINISTRADOR').exists():
            return True

        # DIREÃ‡ÃƒO - acesso total
        if user.groups.filter(name='DIREÃ‡ÃƒO').exists():
            return True

        # O proprietÃ¡rio sempre pode ver sua prÃ³pria timesheet
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
        # Em caso de erro, nega por seguranÃ§a
        return False




def build_timesheet_view_data(timesheet):
    """
    Build complete timesheet view data with analytics
    """
    tasks = timesheet.tasks.select_related('project', 'activity').all()

    # Calcular mÃ©tricas bÃ¡sicas
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

    # Analytics - Horas diÃ¡rias
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

    # ComentÃ¡rios
    comments = [
        {
            "id": comment.id,
            "author_name": comment.author.get_full_name() or comment.author.username,
            "content": comment.content,
            "created_at": comment.created_at
        }
        for comment in timesheet.comments.all().order_by('-created_at')
    ]

    # HistÃ³rico de status
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
        # InformaÃ§Ãµes bÃ¡sicas
        "id": timesheet.id,
        "employee_name": timesheet.employee.get_full_name() or timesheet.employee.username,
        "department_name": timesheet.department.name,
        "status": timesheet.status,
        # "period": f"{timesheet.start_date} to {timesheet.end_date}",
        "submitted_at": timesheet.submitted_at.strftime('%d-%m-%Y'),

        # MÃ©tricas
        "total_hours": float(total_hours),
        "work_days": work_days,
        "task_count": task_count,
        "daily_average": round(daily_average, 2),

        # ConteÃºdo
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

        # HistÃ³rico e comentÃ¡rios
        "status_history": status_history,
        "comments": comments,
    }


########################### EXPORT ################################################


@router.get("timesheets/{timesheet_id}/export-pdf")
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

        # Se nÃ£o encontrar na raiz do media, tenta em subpastas
        if not logo_exists:
            logo_path = os.path.join(settings.MEDIA_ROOT, 'logos', 'logo.png')
            logo_exists = os.path.isfile(logo_path)

        # ---------- Buffer e documento ----------
        buffer = io.BytesIO()

        # Margens generosas para header/rodapÃ©
        left, right, top, bottom = 72, 72, 110, 90
        doc = BaseDocTemplate(
            buffer, pagesize=A4,
            leftMargin=left, rightMargin=right,
            topMargin=top, bottomMargin=bottom
        )

        # Ãrea Ãºtil (frame) onde o conteÃºdo entra (exclui header/footer)
        frame = Frame(doc.leftMargin, doc.bottomMargin,
                      doc.width, doc.height, id='normal')

        # ---------- FunÃ§Ãµes de desenho ----------
        def draw_header(canvas, doc_):
            page_w, page_h = A4

            # Logo - posiÃ§Ã£o ajustada
            if logo_exists:
                try:
                    # Posiciona o logo no canto superior esquerdo
                    canvas.drawImage(
                        logo_path,
                        doc_.leftMargin, page_h - top + 15,  # Ajuste na posiÃ§Ã£o Y
                        width=120,
                        height=40,  # Altura um pouco maior para melhor proporÃ§Ã£o
                        preserveAspectRatio=True,
                        mask='auto'
                    )
                except Exception as e:
                    # Fallback se houver erro com a imagem
                    canvas.setFillColor(colors.red)
                    canvas.setFont("Helvetica", 8)
                    canvas.drawString(doc_.leftMargin, page_h - top + 25, f"[Logo error: {e}]")

            # TÃ­tulo do documento no header (lado direito)
            canvas.setFillColor(BRAND_PRIMARY)
            canvas.setFont("Helvetica-Bold", 14)
            canvas.drawRightString(page_w - doc_.rightMargin, page_h - top + 30, "TIMESHEET")

            # Linha divisÃ³ria sob o header
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
                # Contar pÃ¡ginas
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
                base_y = 40  # Altura do rodapÃ©

                # Linha acima do rodapÃ©
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

                # PÃ¡gina X de Y (lado direito)
                self.setFont("Helvetica-Bold", 9)
                page_label = f"PÃ¡gina {self._pageNumber} de {total_pages}"
                self.drawRightString(right, base_y + 15, page_label)

                # Data de geraÃ§Ã£o
                self.setFont("Helvetica", 8)
                date_label = f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}"
                self.drawRightString(right, base_y + 5, date_label)

        # PageTemplate com header a cada pÃ¡gina
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

        # ---------- ConteÃºdo ----------
        story = []

        # TÃ­tulo principal (centralizado)
        story.append(Paragraph("RELATÃ“RIO DE TIMESHEET", title_style))
        story.append(Spacer(1, 10))

        # InformaÃ§Ãµes do colaborador
        employee_info = Paragraph(
            f"<b>Colaborador:</b> {timesheet.employee.get_full_name()}",
            styles['Normal']
        )
        story.append(employee_info)

        # Tabela de informaÃ§Ãµes
        total_horas = sum(t.hour for t in timesheet.tasks.all())
        info_data = [
            ['Departamento:', timesheet.department.name],
            ['Status:', timesheet.status.upper()],
            ['Total de Horas:', f"{total_horas:.1f}h"],
            # ['PerÃ­odo:', f"{timesheet.start_date} a {timesheet.end_date}"],
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
            # CabeÃ§alho da tabela
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
                repeatRows=1  # Repete cabeÃ§alho em todas as pÃ¡ginas
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

        # ObservaÃ§Ãµes
        if getattr(timesheet, 'obs', None) and timesheet.obs.strip():
            story.append(Spacer(1, 20))
            story.append(Paragraph("ObservaÃ§Ãµes", h2_style))
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


@router.get("timesheets/{timesheet_id}/export-excel")
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
            # Sheet de informaÃ§Ãµes bÃ¡sicas
            info_data = {
                'Campo': ['FuncionÃ¡rio', 'Departamento', 'Status', 'Total de Horas', 'Submetido em'],
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
            info_df.to_excel(writer, sheet_name='InformaÃ§Ãµes', index=False)

            # Sheet de tarefas
            tasks = timesheet.tasks.select_related('project', 'activity').all()
            tasks_data = []

            for task in tasks:
                tasks_data.append({
                    'Data': task.created_at.strftime('%d/%m/%Y'),
                    'Projeto': task.project.name,
                    'Atividade': task.activity.name,
                    'Horas': task.hour,
                    # 'DescriÃ§Ã£o': task.description or ''
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
        logger.error(f"Erro ao gerar Excel: {str(e)}")
        return {"error": "Erro interno ao gerar Excel"}, 500






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
#         # Usa filter() para mÃºltiplos IDs
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
@router.post("timesheetsw33-export123")
def export_timesheets12(request, payload: ExportRequest):  # ✅ Recebe o schema
    timesheet_ids = payload.timesheet_ids
    format = payload.format

    return {"ids": timesheet_ids, "format": format}


from django.http import HttpResponse

import pandas as pd
import io



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
#     # Criar arquivo Excel em memÃ³ria
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



@router.post("timesheets-export")
def export_timesheets(request, payload: ExportRequest):
    timesheet_ids = payload.timesheet_ids
    format = payload.format


    # 🔐 SEGURANÇA: Filtrar por permissão (Prevenir IDOR)
    user = request.auth
    queryset = Timesheet.objects.filter(id__in=timesheet_ids)

    if not user.is_administrator:
        # Se for Manager, pode ver do seu departamento
        user_department = getattr(user, 'department', None)
        if user_department and user_department.can_be_approved_by(user):
             queryset = queryset.filter(department=user_department)
        else:
             # Caso contrário, apenas os seus próprios
             queryset = queryset.filter(employee=user)

    timesheets = queryset.select_related('employee', 'department') \
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

    # Criar arquivo Excel com mÃºltiplas abas
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

    # Para CSV, vocÃª pode retornar os timesheets ou tasks
    # Ou criar um arquivo ZIP com ambos
    df_timesheets = pd.DataFrame(timesheet_data)
    csv_output = df_timesheets.to_csv(index=False)

    response = HttpResponse(csv_output, content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="timesheets_export.csv"'
    return response


@router.post("/validate", response={200: dict, 400: dict})
def validate_timesheet_preview(request, data: TimesheetIn):
    """
    Valida uma timesheet SEM criÃ¡-la.
    Ãštil para o frontend mostrar um preview com validaÃ§Ãµes em tempo real.
    """
    try:
        employee = get_object_or_404(User, id=data.employee_id)

        # Executar validaÃ§Ã£o completa
        is_valid, daily_totals, warnings = TimesheetValidator.validate_timesheet_data(
            data.model_dump(), employee_id=data.employee_id
        )

        # Calcular totais agregados (com outros timesheets)
        aggregated_totals = {}
        for task_date, new_hours in daily_totals.items():
            total_daily = TimesheetValidator._get_aggregated_daily_total(
                data.employee_id,
                task_date,
                None,  # NÃ£o excluir nenhuma timesheet
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
        logger.error(f"Erro na validaÃ§Ã£o (preview): {str(e)}")
        raise HttpError(500, f"Erro na validaÃ§Ã£o: {str(e)}")
