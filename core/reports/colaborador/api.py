# dashboard/colaborador/views.py
from typing import List
from ninja import Router
from ninja.pagination import paginate, PageNumberPagination

from core.activity.models import Activity
from core.project.models import Project
from core.reports.api_colaborador import DailyHoursSchema, TaskSimpleSchema, TimesheetSimpleSchema
from core.reports.base.filters import apply_task_filters, fill_missing_dates
from core.reports.base.metrics import calculate_kpis, calculate_daily_hours, calculate_project_hours
from core.reports.base.permissions import check_colaborador_permission
from core.reports.schemas import FilterOptionsSchema, ColaboradorKPISchema, DashboardFilterSchema, \
    FilteredDashboardResponseSchema
from core.reports.schemas_colaborador import ProjectHoursSchema
from core.timesheet.models import Task, Timesheet

router = Router(tags=["Dashboard Colaborador"])


@router.post("/kpis/", response=ColaboradorKPISchema)
def get_colaborador_kpis(request, filters: DashboardFilterSchema):
    """KPIs pessoais do colaborador"""
    user = request.auth

    # Verificar permissão
    check_colaborador_permission(user)

    # Filtrar tasks do usuário
    base_qs = Task.objects.filter(timesheet__employee=user)
    filtered_qs, date_range = apply_task_filters(base_qs, user, filters.dict())

    # Calcular KPIs
    kpis = calculate_kpis(filtered_qs, user, date_range)

    # Adicionar informações do período
    kpis["period"] = date_range

    return kpis

@router.post("/daily-hours/", response=List[DailyHoursSchema])
def get_colaborador_daily_hours(request, filters: DashboardFilterSchema):
    """Horas diárias do colaborador"""
    user = request.auth

    check_colaborador_permission(user)

    base_qs = Task.objects.filter(timesheet__employee=user)
    filtered_qs, date_range = apply_task_filters(base_qs, user, filters.dict())

    # Calcular horas diárias
    daily_data = calculate_daily_hours(filtered_qs, date_range)

    # Preencher dias faltantes
    return fill_missing_dates(daily_data, date_range)

@router.post("/project-hours/", response=List[ProjectHoursSchema])
def get_colaborador_project_hours(request, filters: DashboardFilterSchema):
    """Distribuição por projeto do colaborador"""
    user = request.auth

    check_colaborador_permission(user)

    base_qs = Task.objects.filter(timesheet__employee=user)
    filtered_qs, _ = apply_task_filters(base_qs, user, filters.dict())

    return calculate_project_hours(filtered_qs)

@router.post("/recent-tasks/", response=List[TaskSimpleSchema])
@paginate(PageNumberPagination, page_size=10)
def get_colaborador_recent_tasks(request, filters: DashboardFilterSchema):
    """Tarefas recentes do colaborador"""
    user = request.auth

    check_colaborador_permission(user)

    base_qs = Task.objects.filter(timesheet__employee=user)
    filtered_qs, _ = apply_task_filters(base_qs, user, filters.dict())

    tasks = filtered_qs.select_related('project', 'activity').order_by('-created_at')

    return [
        {
            "id": task.id,
            "project_name": task.project.name if task.project else None,
            "activity_name": task.activity.name if task.activity else None,
            "hour": task.hour,
            "created_at": task.created_at.date()
        }
        for task in tasks
    ]

@router.post("/recent-timesheets/", response=List[TimesheetSimpleSchema])
@paginate(PageNumberPagination, page_size=5)
def get_colaborador_recent_timesheets(request, filters: DashboardFilterSchema):
    """Timesheets recentes do colaborador"""
    user = request.auth

    check_colaborador_permission(user)

    date_range = filters.get_date_range()

    timesheets = Timesheet.objects.filter(
        employee=user,
        created_at__date__gte=date_range['start_date'],
        created_at__date__lte=date_range['end_date']
    ).order_by('-created_at')

    if filters.status:
        timesheets = timesheets.filter(status=filters.status)

    return [
        {
            "id": ts.id,
            "status": ts.status,
            "total_hour": ts.total_hour,
            "created_at": ts.created_at,
            "submitted_at": ts.submitted_at if ts.submitted_at else None,
            "updated_at": ts.updated_at if ts.updated_at else None,
            "obs": ts.obs,
            "employee_name": ts.employee.get_full_name() if ts.employee else None,
            "department_name": ts.employee.department.name if ts.employee and ts.employee.department else None
        }
        for ts in timesheets
    ]

@router.post("/full-dashboard/", response=FilteredDashboardResponseSchema)
def get_colaborador_full_dashboard(request, filters: DashboardFilterSchema):
    """Dashboard completo do colaborador"""
    user = request.auth

    check_colaborador_permission(user)

    # Coletar todos os dados
    kpis = get_colaborador_kpis(request, filters)
    daily_hours = get_colaborador_daily_hours(request, filters)
    project_hours = get_colaborador_project_hours(request, filters)

    # Limitar itens recentes
    from copy import deepcopy
    filters_copy = deepcopy(filters)

    # Recent tasks
    recent_tasks = Task.objects.filter(
        timesheet__employee=user
    ).select_related('project', 'activity').order_by('-created_at')[:10]

    tasks_list = [
        {
            "id": task.id,
            "project_name": task.project.name if task.project else None,
            "activity_name": task.activity.name if task.activity else None,
            "hour": task.hour,
            "created_at": task.created_at.date()
        }
        for task in recent_tasks
    ]

    # Recent timesheets
    recent_timesheets = Timesheet.objects.filter(
        employee=user
    ).order_by('-created_at')[:5]

    timesheets_list = [
        {
            "id": ts.id,
            "status": ts.status,
            "total_hour": ts.total_hour,
            "created_at": ts.created_at,
            "submitted_at": ts.submitted_at if ts.submitted_at else None,
            "updated_at": ts.updated_at if ts.updated_at else None,
            "obs": ts.obs,
            "employee_name": ts.employee.get_full_name() if ts.employee else None,
            "department_name": ts.employee.department.name if ts.employee and ts.employee.department else None
        }
        for ts in recent_timesheets
    ]

    date_range = filters.get_date_range()

    return {
        "kpis": kpis,
        "daily_hours": daily_hours,
        "project_hours": project_hours,
        "recent_tasks": tasks_list,
        "recent_timesheets": timesheets_list,
        "filters_applied": filters,
        "date_range": date_range
    }

@router.get("/filter-options/", response=FilterOptionsSchema)
def get_colaborador_filter_options(request):
    """Opções de filtro para o colaborador"""
    user = request.auth

    # Projetos do colaborador
    projetos = Project.objects.filter(
        task__timesheet__employee=user
    ).distinct().values('id', 'name').order_by('name')

    # Atividades do colaborador
    atividades = Activity.objects.filter(
        task__timesheet__employee=user
    ).distinct().values('id', 'name').order_by('name')

    # Opções de status
    status_options = [
        {"value": "rascunho", "label": "Rascunho"},
        {"value": "submetido", "label": "Submetido"},
        {"value": "aprovado", "label": "Aprovado"},
        {"value": "rejeitado", "label": "Rejeitado"},
    ]

    # Opções de período
    period_options = [
        {"value": "week", "label": "Esta Semana"},
        {"value": "month", "label": "Este Mês"},
        {"value": "quarter", "label": "Este Trimestre"},
        {"value": "year", "label": "Este Ano"},
        {"value": "custom", "label": "Personalizado"},
    ]

    return {
        "projects": list(projetos),
        "activities": list(atividades),
        "status_options": status_options,
        "period_options": period_options
    }