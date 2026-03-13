from django.core.exceptions import PermissionDenied
from ninja import Router, Query
from django.db.models import Q, Sum, Count
from django.db.models import DecimalField
from datetime import timedelta

from rest_framework.decorators import authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication

from .schemas import *
from .base.periods import get_period_date_range, get_period_options, PeriodEnum
from core.timesheet.models import Task, Timesheet

router = Router(tags=["Dashboard"])

# ==================== FUNÇÕES AUXILIARES ====================
def get_authenticated_user(request):
    """Obtém usuário autenticado com fallback seguro"""
    user = request.auth or request.user
    if not user or not user.is_authenticated:
        raise PermissionDenied("Usuário não autenticado")
    return user


def calculate_submission_metrics(user, start_date, end_date):
    """Calcula métricas de submissão de timesheets compatível com SQLite"""

    timesheets_qs = Timesheet.objects.filter(
        employee=user,
        created_at__gte=start_date,
        created_at__lte=end_date
    )

    total_timesheets = timesheets_qs.count()
    submitted_timesheets = timesheets_qs.filter(status='submetido').count()

    submission_rate = (
        (submitted_timesheets / total_timesheets * 100)
        if total_timesheets > 0 else 0
    )

    # Para SQLite, fazer cálculo no Python
    avg_days_to_submit = None

    if submitted_timesheets > 0:
        # Pegar apenas os campos necessários para otimizar
        submitted_timesheets_data = timesheets_qs.filter(
            status='submetido',
            submitted_at__isnull=False,
            created_at__isnull=False
        ).values_list('submitted_at', 'created_at')

        if submitted_timesheets_data:
            total_days = 0
            count = 0

            for submitted_at, created_at in submitted_timesheets_data:
                try:
                    # Converter para data se necessário
                    if hasattr(submitted_at, 'date'):
                        sub_date = submitted_at.date()
                    else:
                        sub_date = submitted_at

                    if hasattr(created_at, 'date'):
                        cre_date = created_at.date()
                    else:
                        cre_date = created_at

                    days_diff = (sub_date - cre_date).days
                    if days_diff >= 0:
                        total_days += days_diff
                        count += 1
                except (TypeError, AttributeError):
                    continue

            if count > 0:
                avg_days_to_submit = total_days / count

    return {
        'total_timesheets': total_timesheets,
        'submitted_timesheets': submitted_timesheets,
        'submission_rate': submission_rate,
        'avg_days_to_submit': avg_days_to_submit
    }

def calculate_work_patterns(tasks_qs):
    """Analisa padrões de trabalho incluindo métricas de eficiência"""

    # Converter para lista para processar no Python
    tasks_data = list(tasks_qs.values('id', 'created_at', 'hour'))

    if not tasks_data:
        return {
            'most_productive_day': None,
            'avg_hours_per_task': None,
            'max_hours_in_day': None,
            'days_with_overwork': 0,
            'max_consecutive_work_days': 0,
            'weekend_hours': Decimal('0.00'),
            'weekend_work_days': 0
        }

    # Calcular média de horas por tarefa
    total_hours = sum(float(task['hour']) for task in tasks_data)
    avg_hours_per_task = total_hours / len(tasks_data)

    # Agrupar por dia da semana e por data
    from collections import defaultdict
    import datetime

    weekday_hours = defaultdict(float)  # 0=Segunda, 6=Domingo
    daily_hours = defaultdict(float)  # data -> horas
    daily_dates = []  # Lista de datas com trabalho

    for task in tasks_data:
        created_at = task['created_at']
        hour = float(task['hour'])

        # Converter para objeto de data
        if isinstance(created_at, str):
            try:
                date_obj = datetime.datetime.fromisoformat(
                    created_at.replace('Z', '+00:00')
                ).date()
            except:
                try:
                    date_obj = datetime.datetime.strptime(
                        created_at.split('T')[0], '%Y-%m-%d'
                    ).date()
                except:
                    continue
        elif hasattr(created_at, 'date'):
            date_obj = created_at.date()
        else:
            date_obj = created_at

        # Acumular horas
        weekday = date_obj.weekday()  # 0=Segunda, 6=Domingo
        weekday_hours[weekday] += hour
        daily_hours[date_obj] += hour
        daily_dates.append(date_obj)

    # Encontrar dia mais produtivo
    most_productive_day = None
    if weekday_hours:
        max_weekday = max(weekday_hours.items(), key=lambda x: x[1])[0]
        day_names = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo']
        most_productive_day = day_names[max_weekday]

    # Encontrar máximo de horas em um dia
    max_hours_in_day = max(daily_hours.values()) if daily_hours else None

    # Calcular novas métricas de eficiência
    days_with_overwork = 0
    weekend_hours_total = Decimal('0.00')
    weekend_work_days_count = 0

    # Dias únicos com trabalho (sem duplicatas)
    unique_work_dates = sorted(set(daily_dates))

    for date_obj, hours in daily_hours.items():
        # Dias com sobrecarga (> 8 horas)
        if hours > 8:
            days_with_overwork += 1

        # Horas em fins de semana
        weekday = date_obj.weekday()
        if weekday >= 5:  # Sábado (5) ou Domingo (6)
            weekend_hours_total += Decimal(str(hours))
            weekend_work_days_count += 1

    # Calcular maior sequência consecutiva de dias com trabalho
    max_consecutive_work_days = 0
    if unique_work_dates:
        current_streak = 1
        max_streak = 1

        for i in range(1, len(unique_work_dates)):
            prev_date = unique_work_dates[i - 1]
            curr_date = unique_work_dates[i]

            # Verificar se são dias consecutivos
            if (curr_date - prev_date).days == 1:
                current_streak += 1
                max_streak = max(max_streak, current_streak)
            else:
                current_streak = 1

        max_consecutive_work_days = max_streak

    return {
        'most_productive_day': most_productive_day,
        'avg_hours_per_task': round(avg_hours_per_task, 2),
        'max_hours_in_day': max_hours_in_day,
        'days_with_overwork': days_with_overwork,
        'max_consecutive_work_days': max_consecutive_work_days,
        'weekend_hours': weekend_hours_total,
        'weekend_work_days': weekend_work_days_count
    }
def calculate_project_metrics(tasks_qs):
    """Calcula métricas por projeto com segurança contra divisão por zero"""

    project_stats = tasks_qs.exclude(
        Q(project__isnull=True) | Q(project__name__isnull=True)
    ).values(
        'project__name'
    ).annotate(
        total_hours=Sum('hour'),
        task_count=Count('id')
    ).order_by('-total_hours')[:10]  # Limitar a 10 projetos

    top_project = None
    top_project_hours = None
    top_project_percentage = None

    if project_stats:
        # Calcular total de horas apenas uma vez
        total_hours_all = tasks_qs.aggregate(
            total=Sum('hour', output_field=DecimalField(max_digits=10, decimal_places=2))
        )['total'] or Decimal('0.00')

        top = project_stats[0]
        top_project = top['project__name'] or "Sem projeto"
        top_project_hours = top['total_hours']

        if total_hours_all > 0:
            top_project_percentage = (
                float(top_project_hours) / float(total_hours_all)
            ) * 100

    return {
        'top_project': top_project,
        'top_project_hours': top_project_hours,
        'top_project_percentage': round(top_project_percentage, 1) if top_project_percentage else None
    }

def generate_insights(kpis_data: Dict[str, Any]) -> List[str]:
    """Gera insights automáticos baseados nos KPIs"""

    insights = []

    # Insight 1: Frequência de trabalho
    if kpis_data.get('work_frequency') is not None:
        freq = kpis_data['work_frequency']
        days_with = kpis_data.get('days_with_tasks', 0)
        days_total = kpis_data.get('days_in_period', 0)

        if days_total > 0:
            if freq < 30:
                insights.append(f"📅 Trabalho concentrado em {days_with} de {days_total} dias ({freq:.1f}%)")
            elif freq > 80:
                insights.append(f"🎯 Excelente consistência! Trabalho em {freq:.1f}% dos dias")
            else:
                insights.append(f"📊 Trabalho registrado em {freq:.1f}% dos dias")

    # Insight 2: Média diária
    avg_daily = kpis_data.get('avg_daily_hours', 0)
    if avg_daily > 0:
        if avg_daily < 4:
            insights.append(f"⏰ Média de {avg_daily:.1f}h/dia - Considere ajustar a carga")
        elif avg_daily > 8:
            insights.append(f"⚠️ Média de {avg_daily:.1f}h/dia - Verifique equilíbrio")
        else:
            insights.append(f"✅ Média saudável de {avg_daily:.1f}h/dia")

    # Insight 3: Projeto principal
    if kpis_data.get('top_project') and kpis_data.get('top_project_percentage'):
        project = kpis_data['top_project']
        percentage = kpis_data['top_project_percentage']
        hours = kpis_data.get('top_project_hours', 0)

        if percentage > 50:
            insights.append(f"🎯 Foco no projeto '{project}' ({percentage:.0f}% do tempo)")
        else:
            insights.append(f"📋 Projeto principal: '{project}' ({hours}h, {percentage:.0f}%)")

    # Insight 4: Submissão de timesheets
    if kpis_data.get('submission_rate') is not None:
        rate = kpis_data['submission_rate']
        pending = kpis_data.get('pending_timesheets', 0)

        if rate == 100:
            insights.append(f"✅ Todos os timesheets submetidos!")
        elif rate >= 80:
            insights.append(f"📤 {rate:.0f}% de submissão - {pending} pendente(s)")
        else:
            insights.append(f"📝 Taxa de submissão: {rate:.0f}% - {pending} para submeter")

    # Insight 5: Dia mais produtivo
    if kpis_data.get('most_productive_day'):
        day = kpis_data['most_productive_day']
        insights.append(f"🚀 Dia mais produtivo: {day}")

    # Insight 6: Dias com sobrecarga (NOVO)
    if kpis_data.get('days_with_overwork', 0) > 0:
        overwork_days = kpis_data['days_with_overwork']
        if overwork_days == 1:
            insights.append(f"⚠️  {overwork_days} dia com carga superior a 8h")
        else:
            insights.append(f"⚠️  {overwork_days} dias com carga superior a 8h")

    # Insight 7: Sequência de trabalho (NOVO)
    if kpis_data.get('max_consecutive_work_days', 0) > 1:
        consecutive = kpis_data['max_consecutive_work_days']
        if consecutive >= 5:
            insights.append(f"🔥 Maior sequência: {consecutive} dias consecutivos!")
        else:
            insights.append(f"📅 Sequência máxima: {consecutive} dias seguidos")

    # Insight 8: Trabalho em fins de semana (NOVO)
    weekend_hours = kpis_data.get('weekend_hours', 0)
    if weekend_hours > 0:
        weekend_days = kpis_data.get('weekend_work_days', 0)
        if weekend_hours > 8:
            insights.append(f"🏠 {weekend_hours}h em {weekend_days} fim(s) de semana")
        else:
            insights.append(f"🌅 {weekend_hours}h trabalhados em fim de semana")

    return insights[:8]  # Limitar a 8 insights

# ==================== ENDPOINT PRINCIPAL ====================
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.get("/colaborador/", response=DashboardResponseSchema)
def get_dashboard(
        request,
        period: PeriodEnum = Query(PeriodEnum.MONTH),
        start_date: Optional[date] = Query(None),
        end_date: Optional[date] = Query(None),
        project_id: Optional[int] = Query(None),
        activity_id: Optional[int] = Query(None),
        status: Optional[str] = Query(None)
):
    """
    Dashboard completo com KPIs focados no autoacompanhamento do colaborador.
    Todos os dados são filtrados pelo período selecionado.
    """

    # 1. Autenticação
    user = get_authenticated_user(request)

    # 2. Criar filtros ANTES de obter o período
    # O schema vai validar as datas
    try:
        filters = DashboardFilterSchema(
            period=period,
            start_date=start_date,
            end_date=end_date,
            project_id=project_id,
            activity_id=activity_id,
            status=status
        )
    except Exception as e:
        # Retornar erro de validação de forma amigável
        from ninja.errors import ValidationError
        raise ValidationError([{"loc": ["query"], "msg": str(e)}])

    # 3. Obter datas do período usando os valores já validados
    date_range = get_period_date_range(
        period=filters.period,
        start_date=filters.start_date,
        end_date=filters.end_date
    )

    period_start = date_range['start_date']
    period_end = date_range['end_date']
    period_label = date_range['label']
    days_in_period = date_range['days_count']

    # Garantir que não há datas futuras
    today = timezone.now().date()
    if period_end > today:
        period_end = today
        if period_start > today:
            period_start = today

    # Recalcular days_in_period após ajuste
    days_in_period = max((period_end - period_start).days + 1, 1)

    # 4. Queries base (com filtros aplicados)

    base_query = Q(
        timesheet__employee=user,
        created_at__gte=period_start,  # Especifique a tabela
        created_at__lte=period_end
    )
    if filters.project_id:
        base_query &= Q(project_id=filters.project_id)
    if filters.activity_id:
        base_query &= Q(activity_id=filters.activity_id)
    if filters.status:
        base_query &= Q(timesheet__status=filters.status)

    tasks_qs = Task.objects.filter(base_query).select_related(
        'project', 'activity', 'timesheet'
    )

    print(tasks_qs, 'tarefas')

    # 5. Calcular KPIs
    # 5.1. Produtividade básica
    total_hours_result = tasks_qs.aggregate(
        total=Sum('hour', output_field=DecimalField(max_digits=10, decimal_places=2))
    )
    total_hours = total_hours_result['total'] or Decimal('0.00')

    days_with_tasks = tasks_qs.dates('created_at', 'day').distinct().count()

    # Evitar divisão por zero
    avg_daily = (
        float(total_hours) / days_in_period
        if days_in_period > 0 else 0
    )

    work_frequency = (
        (days_with_tasks / days_in_period * 100)
        if days_in_period > 0 else 0
    )

    # 5.2. Timesheets
    pending_timesheets = Timesheet.objects.filter(
        employee=user,
        status='rascunho'
    ).count()

    submission_metrics = calculate_submission_metrics(user, period_start, period_end)

    # 5.3. Distribuição por projeto
    project_metrics = calculate_project_metrics(tasks_qs)

    # 5.4. Padrões de trabalho
    work_patterns = calculate_work_patterns(tasks_qs)

    # 5.5. Gerar insights
    kpis_data = {
        'total_hours': total_hours,
        'avg_daily_hours': avg_daily,
        'days_in_period': days_in_period,
        'days_with_tasks': days_with_tasks,
        'work_frequency': work_frequency,
        'pending_timesheets': pending_timesheets,
        'submitted_timesheets': submission_metrics['submitted_timesheets'],
        'submission_rate': submission_metrics['submission_rate'],
        'avg_days_to_submit': submission_metrics['avg_days_to_submit'],
        'top_project': project_metrics['top_project'],
        'top_project_hours': project_metrics['top_project_hours'],
        'top_project_percentage': project_metrics['top_project_percentage'],
        'most_productive_day': work_patterns['most_productive_day'],
        'avg_hours_per_task': work_patterns['avg_hours_per_task'],
        'max_hours_in_day': work_patterns['max_hours_in_day'],
    }

    insights = generate_insights(kpis_data)

    # 6. Dados para gráficos
    # 6.1. Horas por dia
    daily_hours_data = tasks_qs.values('created_at').annotate(
        total_hours=Sum('hour')
    ).order_by('created_at')

    daily_hours = []
    current_date = period_start
    day_names = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]

    # Criar dicionário para lookup rápido
    daily_dict = {item['created_at']: item['total_hours'] for item in daily_hours_data}

    while current_date <= period_end:
        hours = daily_dict.get(current_date, Decimal('0.00'))
        weekday = current_date.weekday()
        day_name = day_names[weekday] if weekday < len(day_names) else ""

        daily_hours.append({
            "date": current_date,
            "total_hours": hours,
            "day_name": day_name,
            "is_weekend": weekday >= 5
        })
        current_date += timedelta(days=1)

    # 6.2. Horas por projeto
    project_hours_data = tasks_qs.exclude(
        Q(project__isnull=True) | Q(project__name__isnull=True)
    ).values(
        'project__name'
    ).annotate(
        total_hours=Sum('hour', output_field=DecimalField(max_digits=10, decimal_places=2)),
        task_count=Count('id')
    ).order_by('-total_hours')[:7]  # Limitar a 7 projetos para gráfico

    project_hours = []
    colors = ['#3B82F6', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6', '#EC4899', '#14B8A6']

    for idx, item in enumerate(project_hours_data):
        total_hours_all = float(total_hours) if total_hours else 1.0  # Evitar divisão por zero
        percentage = (
            (float(item['total_hours']) / total_hours_all * 100)
            if total_hours_all > 0 else 0
        )

        project_hours.append({
            "project_name": item['project__name'],
            "total_hours": item['total_hours'],
            "percentage": round(percentage, 1),
            "task_count": item['task_count'],
            "color": colors[idx % len(colors)]
        })

    # 7. Dados recentes
    # 7.1. Tarefas recentes
    recent_tasks_qs = tasks_qs.order_by('-created_at')[:10]

    recent_tasks = []
    for task in recent_tasks_qs:
        recent_tasks.append({
            "id": task.id,
            "project_name": task.project.name if task.project else None,
            "activity_name": task.activity.name if task.activity else None,
            "hour": task.hour,
            "created_at": task.created_at,
            "timesheet_status": task.timesheet.status if task.timesheet else None
        })

    print(f"DEBUG: Filtrando timesheets de {period_start} a {period_end}")
    # 7.2. Timesheets recentes
    timesheets_query = Q(employee=user)

    # ADICIONE ESTAS DUAS LINHAS para filtrar pelo período (igual às tasks):
    timesheets_query &= Q(created_at__gte=period_start)
    timesheets_query &= Q(created_at__lte=period_end)

    print(f"DEBUG: Query SQL: {Timesheet.objects.filter(timesheets_query).query}")

    recent_timesheets_qs = Timesheet.objects.filter(timesheets_query).order_by('-created_at')[:10]
    print(f"DEBUG: Encontrados {recent_timesheets_qs.count()} timesheets no período")

    if filters.status:
        timesheets_query &= Q(status=filters.status)

    recent_timesheets_qs = Timesheet.objects.filter(timesheets_query).order_by('-created_at')[:10]

    recent_timesheets = []
    for ts in recent_timesheets_qs:
        days_to_submit = None
        if ts.status == 'submetido' and ts.submitted_at and ts.created_at:
            days_to_submit = (ts.submitted_at - ts.created_at).days

        recent_timesheets.append({
            "id": ts.id,
            "status": ts.status,
            "total_hour": ts.total_hour,
            "created_at": ts.created_at,
            "submitted_at": ts.submitted_at if ts.submitted_at else None,
            "days_to_submit": days_to_submit,
            "employee_name": str(ts.employee) if ts.employee else None
        })

    # 8. Montar resposta final
    kpis = ColaboradorKPISchema(
        total_hours=total_hours,
        avg_daily_hours=round(avg_daily, 2),
        days_in_period=days_in_period,
        days_with_tasks=days_with_tasks,
        work_frequency=round(work_frequency, 1),

        # Novas métricas de eficiência
        days_with_overwork=work_patterns['days_with_overwork'],
        max_consecutive_work_days=work_patterns['max_consecutive_work_days'],
        weekend_hours=work_patterns['weekend_hours'],
        weekend_work_days=work_patterns['weekend_work_days'],

        pending_timesheets=pending_timesheets,
        submitted_timesheets=submission_metrics['submitted_timesheets'],
        submission_rate=round(submission_metrics['submission_rate'], 1),
        avg_days_to_submit=(
            round(submission_metrics['avg_days_to_submit'], 1)
            if submission_metrics['avg_days_to_submit'] else None
        ),
        top_project=project_metrics['top_project'],
        top_project_hours=project_metrics['top_project_hours'],
        top_project_percentage=project_metrics['top_project_percentage'],
        most_productive_day=work_patterns['most_productive_day'],
        avg_hours_per_task=(
            round(work_patterns['avg_hours_per_task'], 2)
            if work_patterns['avg_hours_per_task'] else None
        ),
        max_hours_in_day=work_patterns['max_hours_in_day'],
        period_label=period_label,
        insights=insights
    )

    return DashboardResponseSchema(
        kpis=kpis,
        daily_hours=daily_hours,
        project_hours=project_hours,
        recent_tasks=recent_tasks,
        recent_timesheets=recent_timesheets,
        filters_applied=filters,
        date_range={"start_date": period_start, "end_date": period_end},
        generated_at=timezone.now()
    )

# ==================== ENDPOINT SIMPLES ====================
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.get("/filter-options/", response=FilterOptionsSchema)
def get_filter_options(request):
    """Retorna opções de filtro disponíveis"""
    user = get_authenticated_user(request)

    # Projetos
    projects = Task.objects.filter(
        timesheet__employee=user
    ).exclude(
        Q(project__isnull=True) | Q(project__name__isnull=True)
    ).values(
        'project_id', 'project__name'
    ).distinct().order_by('project__name')

    projects_list = [
        {"id": p['project_id'], "name": p['project__name']}
        for p in projects
    ]

    # Atividades
    activities = Task.objects.filter(
        timesheet__employee=user
    ).exclude(
        Q(activity__isnull=True) | Q(activity__name__isnull=True)
    ).values(
        'activity_id', 'activity__name'
    ).distinct().order_by('activity__name')

    activities_list = [
        {"id": a['activity_id'], "name": a['activity__name']}
        for a in activities
    ]

    # Status
    status_options = [
        {"value": "rascunho", "label": "Rascunho"},
        {"value": "submetido", "label": "Submetido"},
    ]

    # Períodos
    period_options = get_period_options()

    return FilterOptionsSchema(
        projects=projects_list,
        activities=activities_list,
        status_options=status_options,
        period_options=period_options
    )

@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.get("/test/")
def test_endpoint(request):
    """Endpoint de teste"""
    user = get_authenticated_user(request)

    return {
        "status": "ok",
        "user": {
            "id": user.id,
            "username": user.username,
            "full_name": user.get_full_name(),
            "department": user.department.name if hasattr(user, 'department') and user.department else None
        },
        "timestamp": timezone.now().isoformat(),
        "message": "Dashboard API está funcionando!"
    }
