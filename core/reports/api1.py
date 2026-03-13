from typing import Optional
from ninja import Router
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, DateField, DateTimeField
from django.db.models.functions import Cast
from pydantic.schema import Decimal, List
from rest_framework.decorators import authentication_classes, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication

from .schemas import ColaboradorKPISchema, DailyHoursSchema, ProjectHoursSchema, TaskSimpleSchema, \
    TimesheetSimpleSchema, ColaboradorDashboardSchema, DashboardFilterSchema, PeriodEnum, \
    FilteredDashboardResponseSchema, FilterOptionsSchema
from ..activity.models import Activity
from ..project.models import Project
from ..timesheet.models import Task, Timesheet
from django.utils import timezone

from datetime import timedelta, date

router = Router(tags=["Dashboard"])

@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.get("/colaborador/kpis/", response=ColaboradorKPISchema)
def get_colaborador_kpis(request, period: str = "month"):
    """Retorna os KPIs principais do colaborador"""

    user = request.auth
    if not user.is_authenticated:
        raise PermissionDenied("Usuário não autenticado")

    #user = request.user
    hoje = timezone.now().date()

    # Filtros de período
    if period == "week":
        inicio_periodo = hoje - timedelta(days=hoje.weekday())  # Segunda-feira
    else:  # month (default)
        inicio_periodo = hoje.replace(day=1)

    # Total horas no período
    total_horas_periodo = Task.objects.filter(
        timesheet__employee=user.pk,
        created_at__gte=inicio_periodo,
        created_at__lte=hoje
    ).aggregate(total=Sum('hour'))['total'] or Decimal('0.00')

    # Total horas na semana atual
    inicio_semana = hoje - timedelta(days=hoje.weekday())
    total_horas_semana = Task.objects.filter(
        timesheet__employee=user,
        created_at__gte=inicio_semana,
        created_at__lte=hoje
    ).aggregate(total=Sum('hour'))['total'] or Decimal('0.00')

    # Timesheets pendentes (rascunho)
    pendentes = Timesheet.objects.filter(
        employee=user,
        status='rascunho'
    ).count()

    # Timesheets submetidos
    submetidos = Timesheet.objects.filter(
        employee=user,
        status='submetido',
        created_at__gte=inicio_periodo
    ).count()

    # Média diária de horas
    dias_trabalhados = Task.objects.filter(
        timesheet__employee=user,
        created_at__gte=inicio_periodo
    ).values('created_at').distinct().count()

    media_diaria = float(total_horas_periodo) / dias_trabalhados if dias_trabalhados > 0 else 0

    return {
        "total_hours_period": total_horas_periodo,  # Mudado de total_hours_month
        "total_hours_week": total_horas_semana,
        "pending_timesheets": pendentes,
        "submitted_timesheets": submetidos,
        "avg_daily_hours": round(media_diaria, 2)
    }

@router.get("/colaborador/daily-hours/", response=List[DailyHoursSchema])
def get_colaborador_daily_hours(request, days: int = 7):
    """Horas por dia dos últimos N dias"""
    user = request.auth


    hoje = timezone.now().date()
    data_inicio = hoje - timedelta(days=days - 1)

    # Usando Cast para evitar problemas com TruncDate no SQLite
    daily_hours = Task.objects.filter(
        timesheet__employee=user,
        created_at__gte=data_inicio,
        created_at__lte=hoje
    ).annotate(
        date=Cast('created_at', DateField())
    ).values('date').annotate(
        total_hours=Sum('hour')
    ).order_by('date')

    # Preenche dias sem registros com zero
    result = []
    current_date = data_inicio

    # Dicionário para lookup rápido
    daily_dict = {str(item['date']): item['total_hours'] for item in daily_hours}

    while current_date <= hoje:
        horas_dia = daily_dict.get(current_date.isoformat(), Decimal('0.00'))
        result.append({
            "date": current_date,
            "total_hours": horas_dia
        })
        current_date += timedelta(days=1)

    return result

@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.get("/colaborador/project-hours/", response=List[ProjectHoursSchema])
def get_colaborador_project_hours(request, period: str = "month"):
    """Distribuição de horas por projeto"""
    user = request.auth
    hoje = timezone.now().date()

    if period == "week":
        inicio = hoje - timedelta(days=hoje.weekday())
    else:  # month
        inicio = hoje.replace(day=1)

    # Total horas do usuário no período
    total_horas_usuario = Task.objects.filter(
        timesheet__employee=user,
        created_at__gte=inicio,
        created_at__lte=hoje
    ).aggregate(total=Sum('hour'))['total'] or Decimal('0.00')

    # Horas por projeto
    project_hours = Task.objects.filter(
        timesheet__employee=user,
        created_at__gte=inicio,
        created_at__lte=hoje
    ).exclude(project__isnull=True).values(
        'project__name'
    ).annotate(
        total_hours=Sum('hour')
    ).order_by('-total_hours')

    result = []
    for item in project_hours:
        percentage = (float(item['total_hours']) / float(total_horas_usuario) * 100) if total_horas_usuario > 0 else 0

        result.append({
            "project_name": item['project__name'] or "Sem projeto",
            "total_hours": item['total_hours'],
            "percentage": round(percentage, 1)
        })

    return result

@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.get("/colaborador/recent-tasks/", response=List[TaskSimpleSchema])
def get_colaborador_recent_tasks(request, limit: int = 10):
    """Últimas tasks registradas"""
    user = request.auth

    tasks = Task.objects.filter(
        timesheet__employee=user
    ).select_related(
        'project', 'activity'
    ).order_by('-created_at')[:limit]

    return [
        {
            "id": task.id,
            "project_name": task.project.name if task.project else None,
            "activity_name": task.activity.name if task.activity else None,
            "hour": task.hour,
            "created_at": task.created_at
        }
        for task in tasks
    ]

@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.get("/colaborador/recent-timesheets/", response=List[TimesheetSimpleSchema])
def get_colaborador_recent_timesheets(request, limit: int = 5):
    """Últimos timesheets"""
    user = request.auth

    timesheets = Timesheet.objects.filter(
        employee=user
    ).order_by('-created_at')[:limit]

    return [
        {
            "id": ts.id,
            "status": ts.status,
            "total_hour": ts.total_hour,
            "created_at": ts.created_at,
            "submitted_at": ts.submitted_at
        }
        for ts in timesheets
    ]

@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.get("/colaborador/full-dashboard/", response=ColaboradorDashboardSchema)
def get_colaborador_full_dashboard(request):
    """Endpoint completo do dashboard (tudo em uma chamada)"""
    user = request.user

    # Busca todos os dados em paralelo (poderia usar async depois)
    kpis = get_colaborador_kpis(request)
    daily_hours = get_colaborador_daily_hours(request)
    project_hours = get_colaborador_project_hours(request)
    recent_tasks = get_colaborador_recent_tasks(request)
    recent_timesheets = get_colaborador_recent_timesheets(request)

    return {
        "kpis": kpis,
        "daily_hours": daily_hours,
        "project_hours": project_hours,
        "recent_tasks": recent_tasks,
        "recent_timesheets": recent_timesheets
    }


# Endpoint para autenticação via cookie/session (se quiser usar templates)
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.get("/colaborador/session-data/", response=ColaboradorDashboardSchema)
@login_required
def get_colaborador_session_data(request):
    """Versão que usa session/cookie do Django (para templates)"""
    # Reusa as mesmas funções, mas com request.user da session
    return get_colaborador_full_dashboard(request)


#################################### APIs COM TONERS - COLABORADORES  FILTROS#########################################################################

def is_datetime_field(model_class, field_name):
    """Verifica se um campo é DateTimeField"""
    try:
        field = model_class._meta.get_field(field_name)
        return isinstance(field, DateTimeField)
    except:
        return False

def filter_by_date_range(queryset, start_date, end_date, field_name='created_at'):
    """Filtra um queryset por intervalo de datas de forma segura"""
    if is_datetime_field(queryset.model, field_name):
        return queryset.filter(
            **{f'{field_name}__date__gte': start_date,
               f'{field_name}__date__lte': end_date}
        )
    else:
        return queryset.filter(
            **{f'{field_name}__gte': start_date,
               f'{field_name}__lte': end_date}
        )

def apply_filters_to_queryset(queryset, filters: DashboardFilterSchema, user):
    """Aplica filtros ao queryset baseado no DashboardFilterSchema"""

    print(f"\n=== APPLYING FILTERS ===")
    print(f"Model: {queryset.model.__name__}")
    print(f"User: {user}")

    # SEMPRE começa filtrando pelo usuário
    queryset = queryset.filter(timesheet__employee=user)
    print(f"Após filtro de usuário: {queryset.count()} registros")

    # Filtro de datas - created_at é DateField, não DateTimeField!
    date_range = filters.get_date_range()

    # PARA DateField, usamos __gte e __lte diretamente, SEM __date
    queryset = queryset.filter(
        created_at__gte=date_range['start_date'],
        created_at__lte=date_range['end_date']
    )

    print(f"Após filtro de data ({date_range['start_date']} a {date_range['end_date']}): {queryset.count()} registros")

    # Filtros opcionais
    if filters.project_id:
        print(f"Aplicando filtro de projeto: {filters.project_id}")
        queryset = queryset.filter(project_id=filters.project_id)
        print(f"Após filtro de projeto: {queryset.count()} registros")

    if filters.activity_id:
        print(f"Aplicando filtro de atividade: {filters.activity_id}")
        queryset = queryset.filter(activity_id=filters.activity_id)
        print(f"Após filtro de atividade: {queryset.count()} registros")

    if filters.status:
        print(f"Aplicando filtro de status: {filters.status}")
        queryset = queryset.filter(timesheet__status=filters.status)
        print(f"Após filtro de status: {queryset.count()} registros")

    return queryset


@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.post("/colaborador/kpis/", response=ColaboradorKPISchema)
def get_colaborador_kpis_with_filters(request, filters: DashboardFilterSchema):
    """Retorna os KPIs principais do colaborador com filtros"""

    user = request.auth
    if not user.is_authenticated:
        raise PermissionDenied("Usuário não autenticado")

    print(f"\n=== DEBUG KPIs ===")
    print(f"Usuário: {user}")

    date_range = filters.get_date_range()
    inicio_periodo = date_range['start_date']
    fim_periodo = date_range['end_date']

    print(f"Período: {inicio_periodo} a {fim_periodo}")

    # Base queryset para todas as consultas
    base_qs = Task.objects.all()
    base_qs = apply_filters_to_queryset(base_qs, filters, user)

    print(f"Tasks encontradas após filtros: {base_qs.count()}")

    # Total horas no período
    total_horas_periodo = base_qs.aggregate(
        total=Sum('hour')
    )['total'] or Decimal('0.00')

    print(f"Total horas período: {total_horas_periodo}")

    # Total horas na semana atual
    hoje = timezone.now().date()
    inicio_semana = hoje - timedelta(days=hoje.weekday())

    # Query para horas da semana atual
    semana_qs = Task.objects.filter(timesheet__employee=user)

    # Para DateField, usamos __gte/__lte diretamente
    semana_qs = semana_qs.filter(
        created_at__gte=inicio_semana,
        created_at__lte=hoje
    )

    # Aplica outros filtros opcionais
    if filters.project_id:
        semana_qs = semana_qs.filter(project_id=filters.project_id)
    if filters.activity_id:
        semana_qs = semana_qs.filter(activity_id=filters.activity_id)
    if filters.status:
        semana_qs = semana_qs.filter(timesheet__status=filters.status)

    total_horas_semana = semana_qs.aggregate(
        total=Sum('hour')
    )['total'] or Decimal('0.00')

    print(f"Total horas semana: {total_horas_semana}")

    # Timesheets pendentes (rascunho)
    timesheet_qs = Timesheet.objects.filter(employee=user, status='rascunho')

    # Para DateField, usamos __gte/__lte diretamente
    timesheet_qs = timesheet_qs.filter(
        created_at__gte=inicio_periodo,
        created_at__lte=fim_periodo
    )

    print(f"Timesheets rascunho no período: {timesheet_qs.count()}")

    # Filtros adicionais
    if filters.project_id:
        timesheets_com_projeto = Task.objects.filter(
            project_id=filters.project_id
        ).values_list('timesheet_id', flat=True)
        timesheet_qs = timesheet_qs.filter(id__in=timesheets_com_projeto)
        print(f"Timesheets rascunho com projeto {filters.project_id}: {timesheet_qs.count()}")

    if filters.activity_id:
        timesheets_com_atividade = Task.objects.filter(
            activity_id=filters.activity_id
        ).values_list('timesheet_id', flat=True)
        timesheet_qs = timesheet_qs.filter(id__in=timesheets_com_atividade)

    pendentes = timesheet_qs.count()

    # Timesheets submetidos
    submetidos_qs = Timesheet.objects.filter(
        employee=user,
        status='submetido'
    )

    # Para DateField, usamos __gte/__lte diretamente
    submetidos_qs = submetidos_qs.filter(
        created_at__gte=inicio_periodo,
        created_at__lte=fim_periodo
    )

    # Filtros adicionais
    if filters.project_id:
        timesheets_com_projeto = Task.objects.filter(
            project_id=filters.project_id
        ).values_list('timesheet_id', flat=True)
        submetidos_qs = submetidos_qs.filter(id__in=timesheets_com_projeto)

    if filters.activity_id:
        timesheets_com_atividade = Task.objects.filter(
            activity_id=filters.activity_id
        ).values_list('timesheet_id', flat=True)
        submetidos_qs = submetidos_qs.filter(id__in=timesheets_com_atividade)

    submetidos = submetidos_qs.count()

    # Média diária de horas
    dias_trabalhados = base_qs.values('created_at').distinct().count()
    media_diaria = float(total_horas_periodo) / dias_trabalhados if dias_trabalhados > 0 else 0

    print(f"Dias trabalhados: {dias_trabalhados}")
    print(f"Média diária: {media_diaria}")
    print("=== FIM DEBUG KPIs ===\n")

    return {
        "total_hours_period": total_horas_periodo,
        "total_hours_week": total_horas_semana,
        "pending_timesheets": pendentes,
        "submitted_timesheets": submetidos,
        "avg_daily_hours": round(media_diaria, 2)
    }

@router.post("/colaborador/daily-hours/", response=List[DailyHoursSchema])
def get_colaborador_daily_hours_with_filters(request, filters: DashboardFilterSchema, days: Optional[int] = None):
    """Horas por dia com filtros"""
    user = request.auth

    # Se days foi especificado, sobrescreve o filtro de período
    if days:
        hoje = timezone.now().date()
        data_inicio = hoje - timedelta(days=days - 1)
        filters.start_date = data_inicio
        filters.end_date = hoje
        filters.period = PeriodEnum.CUSTOM

    date_range = filters.get_date_range()
    data_inicio = date_range['start_date']
    hoje = date_range['end_date']

    # Aplica filtros
    base_qs = Task.objects.all()
    base_qs = apply_filters_to_queryset(base_qs, filters, user)

    # Usando Cast para evitar problemas com TruncDate no SQLite
    daily_hours = base_qs.annotate(
        date=Cast('created_at', DateField())
    ).values('date').annotate(
        total_hours=Sum('hour')
    ).order_by('date')

    # Preenche dias sem registros com zero
    result = []
    current_date = data_inicio

    # Dicionário para lookup rápido
    daily_dict = {}
    for item in daily_hours:
        date_key = item['date']
        if isinstance(date_key, date):
            date_key = date_key.isoformat()
        else:
            date_key = str(date_key)
        daily_dict[date_key] = item['total_hours']

    while current_date <= hoje:
        horas_dia = daily_dict.get(current_date.isoformat(), Decimal('0.00'))
        result.append({
            "date": current_date,
            "total_hours": horas_dia
        })
        current_date += timedelta(days=1)

    return result

@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.post("/colaborador/project-hours/", response=List[ProjectHoursSchema])
def get_colaborador_project_hours_with_filters(request, filters: DashboardFilterSchema):
    """Distribuição de horas por projeto com filtros"""
    user = request.auth

    # Aplica filtros
    base_qs = Task.objects.all()
    base_qs = apply_filters_to_queryset(base_qs, filters, user)

    # Total horas do usuário no período
    total_horas_usuario = base_qs.aggregate(
        total=Sum('hour')
    )['total'] or Decimal('0.00')

    # Horas por projeto
    project_hours = base_qs.values(
        'project__id', 'project__name'
    ).annotate(
        total_hours=Sum('hour')
    ).order_by('-total_hours')

    result = []
    for item in project_hours:
        percentage = (float(item['total_hours']) / float(total_horas_usuario) * 100) if total_horas_usuario > 0 else 0

        result.append({
            "project_id": item['project__id'],
            "project_name": item['project__name'] or "Sem projeto",
            "total_hours": item['total_hours'],
            "percentage": round(percentage, 1)
        })

    return result

@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.post("/colaborador/recent-tasks/", response=List[TaskSimpleSchema])
def get_colaborador_recent_tasks_with_filters(request, filters: DashboardFilterSchema, limit: int = 10):
    """Últimas tasks registradas com filtros"""
    user = request.auth

    # Aplica filtros
    base_qs = Task.objects.all()
    base_qs = apply_filters_to_queryset(base_qs, filters, user)

    tasks = base_qs.select_related(
        'project', 'activity'
    ).order_by('-created_at')[:limit]

    return [
        {
            "id": task.id,
            "project_id": task.project.id if task.project else None,
            "project_name": task.project.name if task.project else None,
            "activity_id": task.activity.id if task.activity else None,
            "activity_name": task.activity.name if task.activity else None,
            "hour": task.hour,
            # "description": task.description,
            "created_at": task.created_at
        }
        for task in tasks
    ]

@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.post("/colaborador/recent-timesheets/", response=List[TimesheetSimpleSchema])
def get_colaborador_recent_timesheets_with_filters(request, filters: DashboardFilterSchema, limit: int = 5):
    """Últimos timesheets com filtros"""
    user = request.auth

    date_range = filters.get_date_range()

    print(f"\n=== DEBUG recent-timesheets ===")
    print(f"Usuário: {user}")
    print(f"Data range: {date_range}")
    print(f"Filtro status: {filters.status}")
    print(f"Filtro project_id: {filters.project_id}")

    # Base queryset para timesheets
    timesheet_qs = Timesheet.objects.filter(employee=user)

    print(f"Total timesheets do usuário (sem filtros): {timesheet_qs.count()}")

    # Aplica filtros de data - IMPORTANTE: created_at é DateField, não DateTimeField!
    timesheet_qs = timesheet_qs.filter(
        created_at__gte=date_range['start_date'],
        created_at__lte=date_range['end_date']
    )

    print(f"Após filtro de data: {timesheet_qs.count()} timesheets")

    # Filtros opcionais
    if filters.status:
        timesheet_qs = timesheet_qs.filter(status=filters.status)
        print(f"Após filtro de status '{filters.status}': {timesheet_qs.count()} timesheets")

    if filters.project_id:
        # Timesheets que contêm tasks do projeto especificado
        timesheets_com_projeto = Task.objects.filter(
            project_id=filters.project_id
        ).values_list('timesheet_id', flat=True)
        timesheet_qs = timesheet_qs.filter(id__in=timesheets_com_projeto)
        print(f"Após filtro de projeto {filters.project_id}: {timesheet_qs.count()} timesheets")

    if filters.activity_id:
        # Timesheets que contêm tasks da atividade especificada
        timesheets_com_atividade = Task.objects.filter(
            activity_id=filters.activity_id
        ).values_list('timesheet_id', flat=True)
        timesheet_qs = timesheet_qs.filter(id__in=timesheets_com_atividade)
        print(f"Após filtro de atividade {filters.activity_id}: {timesheet_qs.count()} timesheets")

    timesheets = timesheet_qs.order_by('-created_at')[:limit]
    print(f"Timesheets retornados: {timesheets.count()}")

    # Debug: mostrar alguns timesheets encontrados
    if timesheets.exists():
        print(f"\nSample timesheets encontrados:")
        for ts in timesheets[:3]:  # Mostra apenas os 3 primeiros para debug
            print(f"  - ID: {ts.id}, Status: {ts.status}, Data: {ts.created_at}, "
                  f"Total horas: {ts.total_hour}")

    # Retorna apenas os campos que existem no modelo
    return [
        {
            "id": ts.id,
            "status": ts.status,
            "total_hour": ts.total_hour,
            "created_at": ts.created_at,
            "submitted_at": ts.submitted_at,
            # Estes são os campos que realmente existem:
            "updated_at": ts.updated_at,
            "obs": ts.obs,
            "employee_name": ts.employee_name,  # Propriedade @property do modelo
            "department_name": ts.department_name if hasattr(ts, 'department_name') else None,
        }
        for ts in timesheets
    ]

@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.post("/colaborador/full-dashboard/", response=FilteredDashboardResponseSchema)
def get_colaborador_full_dashboard_with_filters(request, filters: DashboardFilterSchema):
    """Endpoint completo do dashboard com filtros dinâmicos"""
    user = request.auth

    # Busca todos os dados com os filtros aplicados
    kpis = get_colaborador_kpis_with_filters(request, filters)
    daily_hours = get_colaborador_daily_hours_with_filters(request, filters)
    project_hours = get_colaborador_project_hours_with_filters(request, filters)
    recent_tasks = get_colaborador_recent_tasks_with_filters(request, filters)
    recent_timesheets = get_colaborador_recent_timesheets_with_filters(request, filters)

    date_range = filters.get_date_range()

    return {
        "kpis": kpis,
        "daily_hours": daily_hours,
        "project_hours": project_hours,
        "recent_tasks": recent_tasks,
        "recent_timesheets": recent_timesheets,
        "filters_applied": filters,
        "date_range": date_range
    }

@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.get("/colaborador/filter-options/", response=FilterOptionsSchema)
def get_filter_options(request):
    """Retorna opções disponíveis para filtros"""
    user = request.auth

    # Projetos disponíveis para o usuário
    projetos = Project.objects.filter(
        task__timesheet__employee=user
    ).distinct().values('id', 'name').order_by('name')

    # Atividades disponíveis para o usuário
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
