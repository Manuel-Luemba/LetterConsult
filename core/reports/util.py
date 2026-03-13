"""
Funções auxiliares para dashboard de gestores - COMPATÍVEL COM OS TEUS MODELOS
"""
from django.core.exceptions import PermissionDenied
from django.db.models import Q, Sum, Count, F, DecimalField, QuerySet

from django.utils import timezone
from datetime import timedelta, date
from decimal import Decimal
from typing import List, Dict, Any, Optional


from core.erp.models import Department
from core.homepage.models import Position
from core.reports.schemas_manager import DistribuicaoCargoSchema, \
    KPIDepartamentoSchema, IndicadorRiscoSchema, AcaoRecomendadaSchema, AlertaSistemaSchema, DistribuicaoProjetoSchema, \
    EvolucaoDiariaSchema

from core.timesheet.models import Task, Timesheet
from core.user.models import User


def get_authenticated_user(request):
    """Obtém usuário autenticado - mesma do teu código"""
    user = request.auth or request.user
    if not user or not user.is_authenticated:
        raise PermissionDenied("Usuário não autenticado")
    return user

# ==================== FUNÇÕES DE ACESSO E VALIDAÇÃO ====================
def is_manager(user: User) -> bool:
    """Verifica se o usuário é gestor - COMPATÍVEL"""
    return user.groups.filter(name="GESTOR").exists()


def get_manager_departments(user):
    """
    Retorna departamentos que um GESTOR pode acessar
    """
    departments = Department.objects.none()

    # 1. Departamento onde é manager
    try:
        managed_dept = Department.objects.get(manager=user, is_active=True)
        departments = Department.objects.filter(id=managed_dept.id)
    except Department.DoesNotExist:
        pass

    # 2. Departamento onde trabalha (se for diferente)
    if user.department and user.department.is_active:
        if not departments.exists() or user.department.id != departments.first().id:
            departments = departments | Department.objects.filter(id=user.department.id)

    return departments.distinct()


def validate_manager_department_access(user: User, department_id: int) -> Optional[Department]:
    """
    Valida se o gestor tem acesso ao departamento solicitado - COMPATÍVEL
    """
    try:
        department = Department.objects.get(id=department_id)

        # Gestor só pode acessar seu próprio departamento
        if user.department and user.department.id == department_id:
            return department

        return None

    except Department.DoesNotExist:
        return None


def get_department_members(
    department: Department,
    include_manager: bool = False,
    only_active: bool = True
) -> QuerySet[User, User]:
    """
    Retorna todos os membros de um departamento - COMPATÍVEL
    """
    queryset = User.objects.filter(
        department=department,
        is_active=only_active
    )

    # if not include_manager:
    #     # Excluir usuários que são GESTOR
    #     queryset = queryset.exclude(groups__name="GESTOR")

    return queryset


# ==================== CÁLCULO DE MÉTRICAS DE DEPARTAMENTO ====================


def calculate_utilization_rate(total_hours, productive_members_count, days_in_period):
    """Calcula taxa de utilização CORRETA"""
    if productive_members_count == 0 or days_in_period == 0:
        return 0

    # Capacidade teórica (8h/dia por pessoa)
    total_capacity = productive_members_count * days_in_period * 8

    if total_capacity == 0:
        return 0

    utilization = (float(total_hours) / total_capacity) * 100

    # Limitar a 100%
    return min(round(utilization, 1), 100)

# ==================== CÁLCULO DE MÉTRICAS INDIVIDUAIS ====================
def calculate_individual_metrics_per_member(
    members: List[User],
    start_date: date,
    end_date: date
) -> List[Dict[str, Any]]:
    """
    Calcula métricas detalhadas para cada membro - COMPATÍVEL
    """
    member_metrics = []
    days_in_period = (end_date - start_date).days + 1

    for member in members:
        # Tasks do membro - COMPATÍVEL
        tasks_qs = Task.objects.filter(
            timesheet__employee=member,
            created_at__range=[start_date, end_date]
        )

        # Timesheets do membro - COMPATÍVEL
        timesheets_qs = Timesheet.objects.filter(
            employee=member,
            created_at__range=[start_date, end_date]
        )

        # 1. Métricas básicas - COMPATÍVEL
        hours_agg = tasks_qs.aggregate(
            total=Sum('hour', output_field=DecimalField(max_digits=10, decimal_places=2))
        )
        total_hours = hours_agg['total'] or Decimal('0.00')

        # Dias trabalhados - COMPATÍVEL
        work_days = tasks_qs.dates('created_at', 'day').distinct().count()

        # 2. Projeto principal - COMPATÍVEL
        top_project = tasks_qs.exclude(
            Q(project__isnull=True) | Q(project__name__isnull=True)
        ).values('project__name').annotate(
            hours=Sum('hour')
        ).order_by('-hours').first()

        # 3. Dias com sobrecarga (> 8h) - COMPATÍVEL
        # Primeiro agrupa por dia
        daily_hours = tasks_qs.values('created_at').annotate(
            daily_total=Sum('hour')
        )

        days_with_overwork = 0
        for day in daily_hours:
            if day['daily_total'] and float(day['daily_total']) > 8:
                days_with_overwork += 1

        # 4. Horas em fins de semana - COMPATÍVEL
        # Usando week_day: 1=Domingo, 2=Segunda, ..., 7=Sábado
        weekend_hours_agg = tasks_qs.filter(
            created_at__week_day__in=[1, 7]  # Domingo e Sábado
        ).aggregate(
            total=Sum('hour')
        )
        weekend_hours = weekend_hours_agg['total'] or Decimal('0.00')

        # 5. Métricas de timesheet - COMPATÍVEL
        timesheets_stats = timesheets_qs.aggregate(
            total=Count('id'),
            submitted=Count('id', filter=Q(status='submetido')),
            # Calcular atrasos: mais de 7 dias entre created_at e submitted_at
            late_submissions=Count('id', filter=Q(
                status='submetido',
                submitted_at__gt=F('created_at') + timedelta(days=7)
            ))
        )

        # 6. Data da última submissão - COMPATÍVEL
        last_submission = timesheets_qs.filter(
            status='submetido'
        ).order_by('-submitted_at').first()

        # 7. Calcular scores
        submission_rate = 0
        if timesheets_stats['total'] > 0:
            submission_rate = (timesheets_stats['submitted'] / timesheets_stats['total']) * 100

        performance_score = calculate_member_performance_score(
            total_hours, work_days, submission_rate, days_with_overwork
        )

        # 8. Tendência de performance
        performance_trend = get_performance_trend(member, start_date, end_date)

        member_metrics.append({
            "employee_id": member.id,
            "employee_name": member.get_full_name(),
            "position": member.position.name if member.position else None,
            "total_hours": total_hours,
            "work_days": work_days,
            "avg_hours_per_day": (
                float(total_hours) / work_days if work_days > 0 else 0
            ),
            "top_project": top_project['project__name'] if top_project else None,
            "top_project_hours": Decimal(str(top_project['hours'])) if top_project else None,
            "submission_rate": round(submission_rate, 1),
            "late_submissions": timesheets_stats['late_submissions'] or 0,
            "days_with_overwork": days_with_overwork,
            "weekend_hours": weekend_hours,
            "last_submission_date": (
                last_submission.submitted_at
                if last_submission and last_submission.submitted_at
                else None
            ),
            "performance_score": performance_score,
            "performance_trend": performance_trend
        })

    return member_metrics


def calculate_member_performance_score(
    total_hours: Decimal,
    work_days: int,
    submission_rate: float,
    days_with_overwork: int
) -> float:
    """
    Calcula score de performance (0-100) para um membro - COMPATÍVEL
    """
    if work_days == 0:
        return 0

    # 1. Score de produtividade (0-40 pontos)
    avg_daily_hours = float(total_hours) / work_days
    productivity_score = min(avg_daily_hours / 8 * 40, 40)

    # Penalizar sobrecarga
    if days_with_overwork > 0:
        productivity_score *= max(0, 1 - (days_with_overwork / work_days * 0.3))

    # 2. Score de consistência (0-30 pontos)
    consistency_score = min(work_days / 22 * 30, 30)  # 22 dias úteis

    # 3. Score de disciplina (0-30 pontos)
    discipline_score = submission_rate * 0.3

    total_score = productivity_score + consistency_score + discipline_score

    return round(total_score, 1)


def get_performance_trend(member, start_date, end_date):
    """
    Determina tendência de performance (up/down/stable) - COMPATÍVEL
    """
    # Calcular período anterior (mesma duração)
    period_days = (end_date - start_date).days + 1
    prev_start_date = start_date - timedelta(days=period_days)
    prev_end_date = start_date - timedelta(days=1)

    # Calcular métricas para período atual - COMPATÍVEL
    current_tasks = Task.objects.filter(
        timesheet__employee=member,
        created_at__range=[start_date, end_date]
    )
    current_hours_agg = current_tasks.aggregate(total=Sum('hour'))
    current_hours = float(current_hours_agg['total'] or 0)

    # Calcular métricas para período anterior - COMPATÍVEL
    prev_tasks = Task.objects.filter(
        timesheet__employee=member,
        created_at__range=[prev_start_date, prev_end_date]
    )
    prev_hours_agg = prev_tasks.aggregate(total=Sum('hour'))
    prev_hours = float(prev_hours_agg['total'] or 0)

    if prev_hours == 0:
        return "stable"

    change_percentage = ((current_hours - prev_hours) / prev_hours) * 100

    if change_percentage > 10:
        return "up"
    elif change_percentage < -10:
        return "down"
    else:
        return "stable"


# ==================== MÉTRICAS POR CARGO (POSITION) ====================
def calculate_metrics_by_position(
    department: Department,
    start_date: date,
    end_date: date
) -> Dict[str, Any]:
    """
    Calcula métricas agrupadas por cargo (position) - COMPATÍVEL
    """
    # 1. Obter todos os cargos ativos no departamento - COMPATÍVEL
    positions = Position.objects.filter(
        user__department=department,
        user__is_active=True
    ).distinct()

    position_metrics = []
    days_in_period = (end_date - start_date).days + 1

    for position in positions:
        # 2. Usuários com este cargo no departamento - COMPATÍVEL
        users_with_position = User.objects.filter(
            department=department,
            position=position,
            is_active=True
        ).exclude(groups__name="GESTOR")

        if not users_with_position.exists():
            continue

        user_count = users_with_position.count()

        # 3. Tasks destes usuários - COMPATÍVEL
        position_tasks = Task.objects.filter(
            timesheet__employee__in=users_with_position,
            created_at__range=[start_date, end_date]
        )

        # 4. Timesheets destes usuários - COMPATÍVEL
        position_timesheets = Timesheet.objects.filter(
            employee__in=users_with_position,
            created_at__range=[start_date, end_date]
        )

        # 5. Calcular métricas agregadas de horas - COMPATÍVEL
        hours_agg = position_tasks.aggregate(
            total=Sum('hour', output_field=DecimalField(max_digits=10, decimal_places=2))
        )
        total_hours = hours_agg['total'] or Decimal('0.00')

        # 6. Métricas de timesheet - COMPATÍVEL
        submission_agg = position_timesheets.aggregate(
            total=Count('id'),
            submitted=Count('id', filter=Q(status='submetido'))
        )

        submission_rate = 0
        if submission_agg['total'] > 0:
            submission_rate = (submission_agg['submitted'] / submission_agg['total']) * 100

        # 7. Dias trabalhados - COMPATÍVEL
        work_days = position_tasks.dates('created_at', 'day').distinct().count()

        # 8. Calcular utilização - COMPATÍVEL
        capacity = user_count * days_in_period * 8
        utilization_rate = 0
        if capacity > 0:
            utilization_rate = (float(total_hours) / capacity) * 100

        # 9. Projetos principais - COMPATÍVEL
        top_projects = position_tasks.exclude(
            Q(project__isnull=True) | Q(project__name__isnull=True)
        ).values('project__name').annotate(
            hours=Sum('hour')
        ).order_by('-hours')[:3]

        # 10. Adicionar ao resultado
        position_metrics.append({
            "position_id": position.id,
            "position_name": position.name,
            "user_count": user_count,
            "total_hours": total_hours,
            "avg_hours_per_user": (
                float(total_hours) / user_count if user_count > 0 else 0
            ),
            "avg_hours_per_day": (
                float(total_hours) / days_in_period if days_in_period > 0 else 0
            ),
            "work_days": work_days,
            "utilization_rate": round(utilization_rate, 1),
            "submission_rate": round(submission_rate, 1),
            "top_projects": [
                {
                    "name": p['project__name'],
                    "hours": p['hours'],
                    "user_count": position_tasks.filter(
                        project__name=p['project__name']
                    ).values('timesheet__employee').distinct().count()
                }
                for p in top_projects
            ]
        })

    # Ordenar por total de horas
    position_metrics.sort(key=lambda x: float(x['total_hours']), reverse=True)

    return {
        "positions": position_metrics,
        "summary": {
            "total_positions": len(position_metrics),
            "total_users": sum(p['user_count'] for p in position_metrics),
            "total_hours": sum(float(p['total_hours']) for p in position_metrics),
            "avg_utilization": (
                sum(p['utilization_rate'] for p in position_metrics) / len(position_metrics)
                if position_metrics else 0
            )
        }
    }


# ==================== COMPARAÇÃO DE DESEMPENHO ====================
def compare_department_performance(
    department: Department,
    period: str,
    compare_with: str = "previous_period"
) -> Dict[str, Any]:
    """
    Compara desempenho do departamento entre períodos - COMPATÍVEL
    """
    from .base.periods import get_period_date_range

    # 1. Calcular período atual usando sua função existente
    date_range_current = get_period_date_range(period=period)
    start_current = date_range_current['start_date']
    end_current = date_range_current['end_date']

    # 2. Calcular período de comparação
    if compare_with == "previous_period":
        # Mesma duração, período anterior
        days_in_period = (end_current - start_current).days + 1
        start_previous = start_current - timedelta(days=days_in_period)
        end_previous = start_current - timedelta(days=1)

    elif compare_with == "same_period_last_month":
        # Mês anterior, mesma duração
        days_in_period = (end_current - start_current).days + 1
        start_previous = start_current - timedelta(days=30)
        end_previous = start_previous + timedelta(days=days_in_period - 1)

    elif compare_with == "same_period_last_year":
        # Ano anterior, mesma duração
        start_previous = start_current.replace(year=start_current.year - 1)
        end_previous = end_current.replace(year=end_current.year - 1)

    else:
        # Default: período anterior
        days_in_period = (end_current - start_current).days + 1
        start_previous = start_current - timedelta(days=days_in_period)
        end_previous = start_current - timedelta(days=1)

    # 3. Obter membros - COMPATÍVEL
    members = get_department_members(department, only_active=True)

    # 4. Calcular métricas do período atual - COMPATÍVEL
    current_metrics = calculate_department_metrics(
        department=department,
        members=members,
        start_date=start_current,
        end_date=end_current
    )

    # 5. Calcular métricas do período anterior - COMPATÍVEL
    previous_metrics = calculate_department_metrics(
        department=department,
        members=members,
        start_date=start_previous,
        end_date=end_previous
    )

    # 6. Calcular variações
    summary_current = current_metrics['summary']
    summary_previous = previous_metrics['summary']

    changes = calculate_percentage_changes_simple(summary_current, summary_previous)

    # 7. Gerar insights simples
    insights = generate_simple_insights(changes)

    return {
        "comparison_type": compare_with,
        "date_ranges": {
            "current": {
                "start": start_current,
                "end": end_current,
                "label": date_range_current.get('label', '')
            },
            "previous": {
                "start": start_previous,
                "end": end_previous,
                "label": f"{start_previous.strftime('%d/%m/%Y')} - {end_previous.strftime('%d/%m/%Y')}"
            }
        },
        "current_period": {
            "summary": summary_current,
            "efficiency_score": current_metrics.get('efficiency_score')
        },
        "previous_period": {
            "summary": summary_previous,
            "efficiency_score": previous_metrics.get('efficiency_score')
        },
        "changes": changes,
        "insights": insights
    }


def calculate_percentage_changes_simple(current_summary, previous_summary):
    """Calcula variações percentuais simples - COMPATÍVEL"""

    metrics_to_compare = [
        'total_hours',
        'avg_hours_per_member',
        'utilization_rate',
        'submission_rate'
    ]

    changes = {}

    for metric in metrics_to_compare:
        current_value = float(current_summary.get(metric, 0))
        previous_value = float(previous_summary.get(metric, 0))

        # Calcular mudança percentual
        if previous_value != 0:
            percent_change = ((current_value - previous_value) / previous_value) * 100
        else:
            percent_change = 100 if current_value > 0 else 0

        changes[metric] = {
            "current": round(current_value, 2),
            "previous": round(previous_value, 2),
            "percent_change": round(percent_change, 2),
            "trend": "up" if percent_change > 5 else "down" if percent_change < -5 else "stable"
        }

    return changes


def generate_simple_insights(changes):
    """Gera insights simples baseados nas mudanças - COMPATÍVEL"""

    insights = []

    # Insight sobre produtividade
    hours_change = changes.get('total_hours', {}).get('percent_change', 0)
    if hours_change > 20:
        insights.append(f"📈 Produtividade aumentou {hours_change:.1f}%")
    elif hours_change < -20:
        insights.append(f"📉 Produtividade reduziu {abs(hours_change):.1f}%")

    # Insight sobre submissão
    sub_change = changes.get('submission_rate', {}).get('percent_change', 0)
    if sub_change > 10:
        insights.append(f"✅ Taxa de submissão melhorou {sub_change:.1f}%")
    elif sub_change < -10:
        insights.append(f"⚠️ Taxa de submissão piorou {abs(sub_change):.1f}%")

    # Insight sobre utilização
    util_change = changes.get('utilization_rate', {}).get('percent_change', 0)
    if util_change > 15:
        insights.append(f"⚡ Utilização da capacidade aumentou {util_change:.1f}%")
    elif util_change < -15:
        insights.append(f"💤 Utilização da capacidade reduziu {abs(util_change):.1f}%")

    return insights


# ==================== FUNÇÕES AUXILIARES ====================
def get_last_timesheet_date(user: User) -> Optional[date]:
    """Retorna data do último timesheet do usuário - COMPATÍVEL"""
    last_timesheet = Timesheet.objects.filter(
        employee=user
    ).order_by('-created_at').first()

    if last_timesheet:
        return last_timesheet.created_at
    return None


def generate_manager_alerts(department: Department, period: str = "week") -> List[Dict[str, Any]]:
    """Gera alertas proativos para o gestor - COMPATÍVEL"""
    alerts = []

    # Configurar período
    end_date = timezone.now().date()
    if period == "week":
        start_date = end_date - timedelta(days=7)
    elif period == "month":
        start_date = end_date - timedelta(days=30)
    else:
        start_date = end_date - timedelta(days=7)

    # Obter membros
    members = get_department_members(department, include_manager=False)

    # 1. Alertas de timesheet pendente
    for member in members:
        last_timesheet = Timesheet.objects.filter(
            employee=member
        ).order_by('-created_at').first()

        if last_timesheet and last_timesheet.status == 'rascunho':
            days_pending = (timezone.now().date() - last_timesheet.created_at).days

            if days_pending >= 3:
                alerts.append({
                    "id": f"pending_{member.id}",
                    "type": "pending_timesheet",
                    "severity": "high" if days_pending > 7 else "medium",
                    "title": f"Timesheet pendente há {days_pending} dias",
                    "description": f"{member.get_full_name()} não submeteu timesheet desde {last_timesheet.created_at.strftime('%d/%m')}",
                    "affected_members": [member.get_full_name()],
                    "created_at": timezone.now(),
                    "action_required": True
                })

    # 2. Alertas de sobrecarga (última semana)
    for member in members:
        tasks_last_week = Task.objects.filter(
            timesheet__employee=member,
            created_at__range=[start_date, end_date]
        )

        total_hours_agg = tasks_last_week.aggregate(total=Sum('hour'))
        total_hours = float(total_hours_agg['total'] or 0)

        work_days = tasks_last_week.dates('created_at', 'day').distinct().count()

        if work_days > 0:
            avg_daily_hours = total_hours / work_days

            if avg_daily_hours > 9:
                alerts.append({
                    "id": f"overwork_{member.id}",
                    "type": "overwork",
                    "severity": "high" if avg_daily_hours > 10 else "medium",
                    "title": "Possível sobrecarga de trabalho",
                    "description": f"{member.get_full_name()} está com média de {avg_daily_hours:.1f}h/dia na última semana",
                    "affected_members": [member.get_full_name()],
                    "created_at": timezone.now(),
                    "action_required": True
                })

    return alerts[:10]
########################################
def calculate_department_metrics(
        department: Department,
        members: List[User],
        start_date: date,
        end_date: date
) -> Dict[str, Any]:
    """
    Calcula métricas agregadas para todo o departamento - VERSÃO FINAL CORRIGIDA
    """
    print(f"=== DEBUG: calculate_department_metrics ===")
    print(f"Membros recebidos: {len(members)}")
    for m in members:
        print(f"  - {m.get_full_name()} (Gestor: {m.groups.filter(name='GESTOR').exists()})")

    # 1. Separar gestores e não-gestores
    gestores = [m for m in members if m.groups.filter(name='GESTOR').exists()]
    nao_gestores = [m for m in members if not m.groups.filter(name='GESTOR').exists()]

    print(f"Gestores: {len(gestores)}, Não-gestores: {len(nao_gestores)}")

    # 2. Obter TODAS as tasks do período (todos os membros)
    tasks = Task.objects.filter(
        timesheet__employee__in=members,
        created_at__range=[start_date, end_date]
    )

    print(f"Tasks encontradas: {tasks.count()}")

    # 3. Obter TODOS os timesheets do período (todos os membros)
    timesheets = Timesheet.objects.filter(
        employee__in=members,
        created_at__range=[start_date, end_date]
    )

    # 4. Calcular horas totais
    hours_agg = tasks.aggregate(
        total_hours=Sum('hour', output_field=DecimalField(max_digits=10, decimal_places=2))
    )
    total_hours = hours_agg['total_hours'] or Decimal('0.00')

    print(f"Total horas: {total_hours}")

    # 5. Calcular dias no período
    days_in_period = max((end_date - start_date).days + 1, 1)

    # 6. Calcular QUEM realmente trabalhou (qualquer membro, incluindo gestores)
    # IDs de TODOS os membros que têm tasks
    all_member_ids_with_tasks = tasks.values_list('timesheet__employee', flat=True).distinct()
    members_with_work = User.objects.filter(id__in=all_member_ids_with_tasks).count()

    print(f"Membros com trabalho: {members_with_work}")
    print(f"IDs com tasks: {list(all_member_ids_with_tasks)}")

    # 7. Calcular taxa de submissão (todos os membros que têm timesheets)
    submission_agg = timesheets.aggregate(
        total=Count('id'),
        submitted=Count('id', filter=Q(status='submetido'))
    )

    submission_rate = 0
    if submission_agg['total'] > 0:
        submission_rate = (submission_agg['submitted'] / submission_agg['total']) * 100

    print(f"Submission rate: {submission_rate}%")

    # 8. Média de dias para submissão
    avg_days_to_submit = None
    submitted_timesheets = timesheets.filter(
        status='submetido',
        submitted_at__isnull=False
    )

    if submitted_timesheets.exists():
        total_days = 0
        count = 0
        for ts in submitted_timesheets:
            if ts.submitted_at and ts.created_at:
                days_diff = (ts.submitted_at - ts.created_at).days
                if days_diff >= 0:
                    total_days += days_diff
                    count += 1
        if count > 0:
            avg_days_to_submit = total_days / count

    # 9. Distribuição por projeto (usar TODAS as tasks)
    project_distribution = calculate_project_distribution(tasks, members, total_hours)

    print(f"Project distribution items: {len(project_distribution)}")

    # 10. Identificar riscos (apenas para não-gestores)
    risk_indicators = identify_department_risks(members, start_date, end_date)

    # 11. Calcular eficiência (baseado em não-gestores)


    efficiency_score = calculate_department_efficiency(
        tasks, nao_gestores, days_in_period, start_date, end_date
    )

    # 12. Calcular métricas de resumo CORRETAS
    avg_hours_per_working_member = 0
    if members_with_work > 0:
        avg_hours_per_working_member = float(total_hours) / members_with_work

    avg_hours_per_day = 0
    if days_in_period > 0:
        avg_hours_per_day = float(total_hours) / days_in_period

    utilization_rate = 0
    if members_with_work > 0 and days_in_period > 0:
        total_capacity = members_with_work * days_in_period * 8
        if total_capacity > 0:
            utilization_rate = min((float(total_hours) / total_capacity) * 100, 100)

    total_projects = tasks.values('project').distinct().count()

    print(f"=== RESUMO ===")
    print(f"Total membros: {len(members)}")
    print(f"Com trabalho: {members_with_work}")
    print(f"Horas: {total_hours}")
    print(f"Projetos: {total_projects}")
    print(f"Distribuição: {len(project_distribution)} itens")
    print("==============\n")

    return {
        "summary": {
            "total_members": len(members),
            "active_members": members_with_work,  # QUALQUER membro com tasks
            "total_hours": total_hours,
            "avg_hours_per_member": round(avg_hours_per_working_member, 1),
            "avg_hours_per_day": round(avg_hours_per_day, 2),
            "utilization_rate": round(utilization_rate, 1),
            "total_projects": total_projects,
            "submission_rate": round(submission_rate, 1),
            "approval_rate": None,
            "avg_days_to_submit": round(avg_days_to_submit, 1) if avg_days_to_submit else None
        },
        "project_distribution": project_distribution,
        "risk_indicators": risk_indicators,
        "efficiency_score": efficiency_score
    }


def calculate_project_distribution(tasks, members, total_hours_all):
    """Calcula distribuição por projeto - VERSÃO CORRIGIDA"""
    print(f"=== DEBUG calculate_project_distribution ===")
    print(f"Tasks recebidas: {tasks.count()}")
    print(f"Total horas all: {total_hours_all}")

    if not tasks.exists():
        print("Nenhuma task, retornando []")
        return []

    # Usar tasks.filter em vez de tasks.exclude para debug
    tasks_with_projects = tasks.exclude(
        Q(project__isnull=True) | Q(project__name__isnull=True)
    )
    print(f"Tasks com projetos: {tasks_with_projects.count()}")

    if tasks_with_projects.count() == 0:
        print("Nenhuma task com projeto, retornando []")
        return []

    project_stats = tasks_with_projects.values(
        'project__name'
    ).annotate(
        total_hours=Sum('hour'),
        member_count=Count('timesheet__employee', distinct=True)
    ).order_by('-total_hours')[:10]

    print(f"Project stats encontrados: {len(project_stats)}")

    distribution = []
    for stat in project_stats:
        percentage = 0
        if total_hours_all and float(total_hours_all) > 0:
            percentage = (float(stat['total_hours']) / float(total_hours_all)) * 100

        avg_hours_per_member = 0
        if stat['member_count'] > 0:
            avg_hours_per_member = float(stat['total_hours']) / stat['member_count']

        distribution.append({
            "project_name": stat['project__name'],
            "total_hours": stat['total_hours'],
            "member_count": stat['member_count'],
            "percentage": round(percentage, 1),
            "avg_hours_per_member": round(avg_hours_per_member, 1)
        })

        print(f"  - '{stat['project__name']}': {stat['total_hours']}h ({percentage:.1f}%)")

    print(f"Retornando {len(distribution)} itens na distribuição")
    return distribution
############################################

def identify_department_risks(members, start_date, end_date):
    """Identifica riscos no departamento - CORRIGIDO COMPLETO"""
    risks = []
    days_in_period = (end_date - start_date).days + 1

    # Filtrar apenas membros não gestores para análise de riscos
    non_manager_members = members.exclude(groups__name="GESTOR")

    for member in non_manager_members:
        # 1. Analisar tasks do membro
        member_tasks = Task.objects.filter(
            timesheet__employee=member,
            created_at__range=[start_date, end_date]
        )

        # Se não tem tasks, é risco de INATIVIDADE
        if not member_tasks.exists():
            existing_risk = next((r for r in risks if r['type'] == 'inactivity'), None)

            if existing_risk:
                existing_risk['count'] += 1
                existing_risk['affected_members'].append(member.get_full_name())
            else:
                risks.append({
                    "type": "inactivity",
                    "severity": "medium",
                    "count": 1,
                    "description": "Membros sem registo de horas no período",
                    "affected_members": [member.get_full_name()]
                })
            continue

        # Calcular dias EFETIVAMENTE trabalhados
        work_days = member_tasks.dates('created_at', 'day').distinct().count()

        # Horas totais
        total_hours_agg = member_tasks.aggregate(total=Sum('hour'))
        total_hours = float(total_hours_agg['total'] or 0)

        # 2. Verificar sobrecarga (> 8h/dia em média NOS DIAS TRABALHADOS)
        if work_days > 0:
            avg_hours_per_work_day = total_hours / work_days

            # Só verificar sobrecarga se trabalhou pelo menos 5 dias
            if work_days >= 5 and avg_hours_per_work_day > 9:
                severity = "high" if avg_hours_per_work_day > 10 else "medium"

                existing_risk = next((r for r in risks if r['type'] == 'overwork'), None)

                if existing_risk:
                    existing_risk['count'] += 1
                    existing_risk['affected_members'].append(member.get_full_name())
                else:
                    risks.append({
                        "type": "overwork",
                        "severity": severity,
                        "count": 1,
                        "description": f"Membros com média >9h/dia nos dias trabalhados",
                        "affected_members": [member.get_full_name()]
                    })

            # 3. Verificar subutilização (< 4h/dia NOS DIAS TRABALHADOS)
            # Só se trabalhou em mais de 5 dias (para ter significado estatístico)
            if work_days >= 5 and avg_hours_per_work_day < 4:
                existing_risk = next((r for r in risks if r['type'] == 'underutilization'), None)

                if existing_risk:
                    existing_risk['count'] += 1
                    existing_risk['affected_members'].append(member.get_full_name())
                else:
                    risks.append({
                        "type": "underutilization",
                        "severity": "medium",
                        "count": 1,
                        "description": f"Membros com média <4h/dia nos dias trabalhados",
                        "affected_members": [member.get_full_name()]
                    })

            # 4. Verificar consistência (menos de 15 dias de trabalho em período longo)
            if days_in_period > 30 and work_days < (days_in_period * 0.3):  # Menos de 30% dos dias
                existing_risk = next((r for r in risks if r['type'] == 'inconsistency'), None)

                if existing_risk:
                    existing_risk['count'] += 1
                    existing_risk['affected_members'].append(member.get_full_name())
                else:
                    risks.append({
                        "type": "inconsistency",
                        "severity": "low",
                        "count": 1,
                        "description": f"Baixa frequência de trabalho ({work_days} de {days_in_period} dias)",
                        "affected_members": [member.get_full_name()]
                    })

        # 5. Verificar atraso na submissão
        last_timesheet = Timesheet.objects.filter(
            employee=member,
            created_at__range=[start_date, end_date]
        ).order_by('-created_at').first()

        if last_timesheet and last_timesheet.status == 'rascunho':
            days_pending = (timezone.now().date() - last_timesheet.created_at).days

            if days_pending > 7:
                severity = "high" if days_pending > 14 else "medium"
                existing_risk = next((r for r in risks if r['type'] == 'late_submission'), None)

                if existing_risk:
                    existing_risk['count'] += 1
                    existing_risk['affected_members'].append(member.get_full_name())
                else:
                    risks.append({
                        "type": "late_submission",
                        "severity": severity,
                        "count": 1,
                        "description": f"Timesheets pendentes há >7 dias",
                        "affected_members": [member.get_full_name()]
                    })

    return risks


def calculate_department_efficiency(tasks, members, days_in_period, start_date, end_date):
    """Calcula score de eficiência do departamento (0-100) - VERSÃO SIMPLIFICADA"""
    # members pode ser lista ou QuerySet
    if not members:
        return 0

    # Se for lista, converter para QuerySet
    if isinstance(members, list):
        if not members:  # lista vazia
            return 0
        member_ids = [m.id for m in members]
        members_qs = User.objects.filter(id__in=member_ids)
    else:
        members_qs = members

    if members_qs.count() == 0 or days_in_period == 0 or not tasks.exists():
        return 0

    member_count = members_qs.count()

    # 1. Produtividade
    total_hours_agg = tasks.aggregate(total=Sum('hour'))
    total_hours = float(total_hours_agg['total'] or 0)

    avg_hours_per_member_per_day = total_hours / (member_count * days_in_period)
    productivity_score = min(avg_hours_per_member_per_day / 8 * 100, 100)

    # 2. Consistência
    work_days = tasks.dates('created_at', 'day').distinct().count()
    consistency_score = (work_days / days_in_period) * 100

    # 3. Submissão
    timesheets = Timesheet.objects.filter(
        employee__in=members_qs,
        created_at__range=[start_date, end_date]
    )
    submission_stats = timesheets.aggregate(
        total=Count('id'),
        submitted=Count('id', filter=Q(status='submetido'))
    )

    submission_score = 0
    if submission_stats['total'] > 0:
        submission_score = (submission_stats['submitted'] / submission_stats['total']) * 100

    # 4. Score final
    efficiency = (
            productivity_score * 0.4 +
            consistency_score * 0.3 +
            submission_score * 0.3
    )

    return round(max(0, min(efficiency, 100)), 1)


# ==================== FUNÇÕES DE ACESSO CORRIGIDAS ====================

def has_dashboard_access(user):
    """
    Verifica se usuário tem acesso ao dashboard
    Baseado nos grupos: ADMINISTRADOR, DIRECTOR, GESTOR
    """
    if user.is_superuser:
        return True

    valid_groups = ['ADMINISTRADOR', 'DIRECTOR', 'GESTOR']
    user_groups = user.groups.values_list('name', flat=True)

    return any(group in valid_groups for group in user_groups)


def get_user_access_level(user):
    """
    Retorna nível de acesso específico:
    - 'admin': ADMINISTRADOR ou superuser
    - 'director': DIRECTOR
    - 'manager': GESTOR
    - None: sem acesso
    """
    if not has_dashboard_access(user):
        return None

    # 1. ADMIN tem prioridade máxima
    if user.is_superuser or user.groups.filter(name="ADMINISTRADOR").exists():
        return 'admin'

    # 2. DIRECTOR
    if user.groups.filter(name="DIRECTOR").exists():
        return 'director'

    # 3. GESTOR
    if user.groups.filter(name="GESTOR").exists():
        return 'manager'

    return None




def get_manager_primary_department(user):
    """
    Retorna departamento principal do gestor
    Prioridade: 1) Onde é manager, 2) Onde trabalha
    """
    try:
        return Department.objects.get(manager=user, is_active=True)
    except Department.DoesNotExist:
        if user.department and user.department.is_active:
            return user.department
    return None


def get_accessible_departments(user):
    """
    Retorna departamentos acessíveis pelo usuário
    """
    access_level = get_user_access_level(user)

    if access_level in ['admin', 'director']:
        # Admin e Director: TODOS departamentos
        return Department.objects.filter(is_active=True).order_by('name')

    elif access_level == 'manager':
        # Gestor: APENAS seus departamentos
        return get_manager_departments(user)

    return Department.objects.none()


def validate_department_access(user, department_id):
    """
    Valida se usuário tem acesso ao departamento
    """
    if not department_id:
        return None

    access_level = get_user_access_level(user)

    if access_level in ['admin', 'director']:
        # Admin/Director pode acessar qualquer departamento
        try:
            return Department.objects.get(id=department_id, is_active=True)
        except Department.DoesNotExist:
            raise PermissionDenied(f"Departamento {department_id} não encontrado")

    elif access_level == 'manager':
        # Gestor só pode acessar seus departamentos
        accessible_departments = get_manager_departments(user)
        try:
            department = accessible_departments.get(id=department_id)
            return department
        except Department.DoesNotExist:
            raise PermissionDenied("Sem acesso a este departamento")

    return None

############################## GESTOR ##########################################


# ==================== FUNÇÕES AUXILIARES COMPLETAS ====================

def calcular_score_produtividade(media_horas_diaria: float) -> float:
    """
    Calcula score de produtividade baseado na média de horas diárias.

    Score de 0-100 baseado em:
    - < 4h/dia: Baixa produtividade (score 0-40)
    - 4-6h/dia: Produtividade moderada (score 40-70)
    - 6-8h/dia: Produtividade ideal (score 70-90)
    - > 8h/dia: Possível sobrecarga (score 90-100, mas com penalização)
    """

    if media_horas_diaria <= 0:
        return 0.0

    if media_horas_diaria < 4:
        # Produtividade baixa: crescimento linear de 0 a 40
        return (media_horas_diaria / 4) * 40

    elif media_horas_diaria < 6:
        # Produtividade moderada: crescimento linear de 40 a 70
        base_score = 40
        adicional = ((media_horas_diaria - 4) / 2) * 30
        return base_score + adicional

    elif media_horas_diaria <= 8:
        # Produtividade ideal: crescimento linear de 70 a 90
        base_score = 70
        adicional = ((media_horas_diaria - 6) / 2) * 20
        return base_score + adicional

    else:
        # Acima de 8h/dia: penalização por possível sobrecarga
        base_score = 90
        # Penalização: -2 pontos por hora acima de 8
        penalizacao = (media_horas_diaria - 8) * 2
        score_final = base_score - penalizacao
        # Garantir que não fique abaixo de 70
        return max(70.0, min(100.0, score_final))


def calcular_dias_uteis(inicio: date, fim: date) -> int:
    """
    Calcula dias úteis entre duas datas (exclui finais de semana).
    Implementação básica - pode ser estendida para considerar feriados.
    """
    from datetime import timedelta

    dias_totais = (fim - inicio).days + 1

    # Contar finais de semana
    dias_fim_semana = 0
    for i in range(dias_totais):
        data = inicio + timedelta(days=i)
        # Sábado=5, Domingo=6
        if data.weekday() >= 5:
            dias_fim_semana += 1

    return dias_totais - dias_fim_semana


def calcular_taxa_utilizacao(total_horas: Decimal, total_funcionarios: int, dias_uteis: int) -> float:
    """
    Calcula taxa de utilização em percentual.

    Fórmula: (horas reais / capacidade total) * 100
    Capacidade total: funcionários * dias úteis * 8 horas por dia
    """
    if total_funcionarios == 0 or dias_uteis == 0:
        return 0.0

    capacidade_total = total_funcionarios * dias_uteis * 8
    if capacidade_total == 0:
        return 0.0

    horas_float = float(total_horas)
    return (horas_float / capacidade_total) * 100


def calcular_taxa_submissao(membros, inicio: date, fim: date) -> float:
    """
    Calcula taxa de submissão de timesheets no período.
    """
    timesheets = Timesheet.objects.filter(
        employee__in=membros,
        created_at__range=[inicio, fim]
    )

    total = timesheets.count()
    if total == 0:
        return 0.0

    submetidos = timesheets.filter(status='submetido').count()
    return (submetidos / total) * 100


def calcular_score_eficiencia(taxa_utilizacao: float, taxa_submissao: float, media_horas: float) -> float:
    """
    Calcula score composto de eficiência.

    Fórmula: média ponderada dos três componentes
    - Utilização: 40%
    - Submissão: 40%
    - Horas otimizadas: 20%
    """
    # Normalizar média de horas (considerar ideal 8 horas)
    # Score de horas: 100% se for 8h, decai se for muito abaixo ou muito acima
    if media_horas <= 0:
        score_horas = 0
    elif media_horas <= 8:
        score_horas = (media_horas / 8) * 100
    else:
        # Acima de 8h: penalização progressiva
        excesso = media_horas - 8
        penalizacao = excesso * 5  # -5% por hora extra
        score_horas = max(50, 100 - penalizacao)

    # Garantir limites
    score_horas = max(0, min(100, score_horas))
    taxa_utilizacao = max(0, min(100, taxa_utilizacao))
    taxa_submissao = max(0, min(100, taxa_submissao))

    # Média ponderada
    peso_utilizacao = 0.4
    peso_submissao = 0.4
    peso_horas = 0.2

    score_final = (
            taxa_utilizacao * peso_utilizacao +
            taxa_submissao * peso_submissao +
            score_horas * peso_horas
    )

    return round(score_final, 1)


def calcular_distribuicao_cargos(departamento: Department, inicio: date, fim: date, membros) -> List[
    DistribuicaoCargoSchema]:
    """
    Calcula distribuição de horas por cargo.
    """
    # Agrupar tarefas por cargo
    tarefas_por_cargo = Task.objects.filter(
        timesheet__employee__in=membros,
        created_at__range=[inicio, fim]
    ).exclude(
        timesheet__employee__position__isnull=True
    ).values(
        'timesheet__employee__position_id',
        'timesheet__employee__position__name'
    ).annotate(
        total_horas=Sum('hour'),
        funcionarios_ativos=Count('timesheet__employee', distinct=True)
    ).order_by('-total_horas')

    # Calcular horas totais para percentuais
    horas_totais = sum(item['total_horas'] or Decimal('0.00') for item in tarefas_por_cargo)

    distribuicao = []
    for item in tarefas_por_cargo:
        horas = item['total_horas'] or Decimal('0.00')
        percentual = (float(horas) / float(horas_totais) * 100) if horas_totais > 0 else 0

        distribuicao.append(
            DistribuicaoCargoSchema(
                cargo_id=item['timesheet__employee__position_id'],
                cargo_nome=item['timesheet__employee__position__name'],
                total_horas=horas,
                funcionarios_ativos=item['funcionarios_ativos'],
                media_horas_cargo=(
                    float(horas) / item['funcionarios_ativos']
                    if item['funcionarios_ativos'] > 0 else 0
                ),
                percentual=percentual
            )
        )

    return distribuicao


def calcular_performance_individual(membros, inicio: date, fim: date) -> List[Dict[str, Any]]:
    """
    Calcula performance individual de cada membro.
    """
    performance_data = []

    for membro in membros:
        # Tarefas do membro no período
        tarefas_membro = Task.objects.filter(
            timesheet__employee=membro,
            created_at__range=[inicio, fim]
        )

        # Métricas básicas
        horas_total = tarefas_membro.aggregate(
            total=Sum('hour')
        )['total'] or Decimal('0.00')

        dias_trabalhados = tarefas_membro.values('created_at__date').distinct().count()
        dias_uteis_periodo = calcular_dias_uteis(inicio, fim)
        media_horas_diaria = float(horas_total) / dias_trabalhados if dias_trabalhados > 0 else 0

        # Timesheets do membro
        timesheets_membro = Timesheet.objects.filter(
            employee=membro,
            created_at__range=[inicio, fim]
        )

        total_timesheets = timesheets_membro.count()
        timesheets_submetidos = timesheets_membro.filter(status='submetido').count()
        taxa_submissao = (timesheets_submetidos / total_timesheets * 100) if total_timesheets > 0 else 0

        # Projetos trabalhados
        projetos_trabalhados = tarefas_membro.values('project').distinct().count()

        # Projeto com mais horas
        top_projeto = tarefas_membro.values(
            'project_id', 'project__name'
        ).annotate(
            horas=Sum('hour')
        ).order_by('-horas').first()

        top_projeto_info = None
        if top_projeto:
            top_projeto_info = {
                "id": top_projeto['project_id'],
                "nome": top_projeto['project__name'],
                "horas": float(top_projeto['horas'] or 0)
            }

        # Horas extras e fim de semana
        horas_extras = Decimal('0.00')
        horas_fim_semana = Decimal('0.00')

        # Implementar cálculo específico se seu modelo suportar

        performance_data.append({
            "funcionario": {
                "id": membro.id,
                "nome_completo": membro.get_full_name(),
                "username": membro.username,
                "email": membro.email,
                "cargo": membro.position.name if membro.position else None,
                "cargo_id": membro.position.id if membro.position else None,
                "ativo": membro.is_active,
                "data_admissao": getattr(membro, 'hire_date', None),
                "avatar_url": get_avatar_url(membro),
                "departamento_id": membro.department.id if membro.department else None,
                "departamento_nome": membro.department.name if membro.department else None
            },
            "total_horas": horas_total,
            "dias_trabalhados": dias_trabalhados,
            "media_horas_diaria": media_horas_diaria,
            "taxa_submissao": taxa_submissao,
            "taxa_aprovacao": None,  # Implementar se tiver status de aprovação
            "projetos_trabalhados": projetos_trabalhados,
            "top_projeto": top_projeto_info,
            "horas_extras": horas_extras,
            "horas_fim_semana": horas_fim_semana
        })

    return performance_data


def filtrar_por_threshold_horas(performance_data: List[Dict[str, Any]],
                                limite_min: Optional[float],
                                limite_max: Optional[float]) -> List[Dict[str, Any]]:
    """
    Filtra dados de performance por threshold de horas.
    """
    if limite_min is None and limite_max is None:
        return performance_data

    filtrados = []
    for item in performance_data:
        media_horas = item['media_horas_diaria']
        incluir = True

        if limite_min is not None and media_horas < limite_min:
            incluir = False

        if limite_max is not None and media_horas > limite_max:
            incluir = False

        if incluir:
            filtrados.append(item)

    return filtrados


def identificar_pontos_destaque(kpis: KPIDepartamentoSchema) -> List[str]:
    """
    Identifica os principais pontos de destaque (positivos) nas métricas.

    Pontos de destaque são conquistas ou métricas excepcionais
    que merecem reconhecimento ou celebração.
    """
    destaques = []

    # 1. Destaque por alta eficiência
    if kpis.score_eficiencia and kpis.score_eficiencia >= 85:
        if kpis.score_eficiencia >= 95:
            nivel = "EXCELENTE"
        elif kpis.score_eficiencia >= 90:
            nivel = "ÓTIMO"
        else:
            nivel = "BOM"

        destaques.append(
            f"{nivel} - Score de eficiência: {kpis.score_eficiencia:.1f} (acima da meta de 80)"
        )

    # 2. Destaque por alta taxa de utilização
    if kpis.taxa_utilizacao >= 85:
        if kpis.taxa_utilizacao >= 95:
            nivel = "EXCEPCIONAL"
        elif kpis.taxa_utilizacao >= 90:
            nivel = "EXCELENTE"
        else:
            nivel = "MUITO BOM"

        destaques.append(
            f"{nivel} - Taxa de utilização: {kpis.taxa_utilizacao:.1f}% (meta: 75%)"
        )

    # 3. Destaque por alta taxa de submissão
    if kpis.taxa_submissao >= 95:
        if kpis.taxa_submissao == 100:
            destaques.append("PERFEITO - 100% dos timesheets submetidos")
        else:
            destaques.append(
                f"EXCELENTE - Taxa de submissão: {kpis.taxa_submissao:.1f}% (próximo da perfeição)"
            )

    # 4. Destaque por consistência (baixa variação/dias sem registros)
    if kpis.dias_sem_registos == 0:
        destaques.append("CONSISTÊNCIA PERFEITA - Todos os dias úteis com registros")
    elif kpis.dias_sem_registos <= kpis.dias_uteis * 0.05:  # Menos de 5% dos dias
        destaques.append("ALTA CONSISTÊNCIA - Apenas poucos dias sem registros")

    # 5. Destaque por produtividade acima da média
    if kpis.media_horas_diaria >= 7.5 and kpis.media_horas_diaria <= 8.5:
        destaques.append("PRODUTIVIDADE IDEAL - Média diária dentro da faixa ótima (7.5-8.5h)")
    elif kpis.media_horas_diaria > 8.5:
        # Cuidado com sobrecarga, mas reconhecer dedicação
        if kpis.media_horas_diaria <= 9.5:
            destaques.append("ALTA DEDICAÇÃO - Média diária acima de 8.5h (monitorar sobrecarga)")

    # 6. Destaque por balanceamento entre funcionários
    if kpis.media_horas_funcionario and kpis.total_horas:
        # Se a média por funcionário está próxima da média geral dividida
        # (indica distribuição equilibrada)
        media_esperada = float(kpis.total_horas) / kpis.total_funcionarios if kpis.total_funcionarios > 0 else 0
        if abs(kpis.media_horas_funcionario - media_esperada) <= 0.5:
            destaques.append("BALANCEAMENTO IDEAL - Distribuição equilibrada de horas entre a equipe")

    # 7. Destaque por número de projetos
    if kpis.total_projetos >= 10:
        if kpis.total_projetos >= 15:
            nivel = "DIVERSIFICAÇÃO AMPLA"
        else:
            nivel = "BOA DIVERSIFICAÇÃO"

        destaques.append(f"{nivel} - Trabalhando em {kpis.total_projetos} projetos simultaneamente")

    # 8. Destaque por relação projetos/ativos
    if kpis.projetos_ativos and kpis.total_projetos:
        percentual_ativos = (kpis.projetos_ativos / kpis.total_projetos) * 100
        if percentual_ativos >= 80:
            destaques.append(f"PORTFÓLIO ATIVO - {percentual_ativos:.0f}% dos projetos em andamento")

    # 9. Destaque por dias trabalhados vs dias úteis
    if kpis.dias_trabalhados == kpis.dias_uteis:
        destaques.append("COBERTURA COMPLETA - Registros em todos os dias úteis do período")
    elif kpis.dias_trabalhados >= kpis.dias_uteis * 0.95:  # 95% ou mais
        cobertura = (kpis.dias_trabalhados / kpis.dias_uteis) * 100
        destaques.append(f"COBERTURA EXCELENTE - {cobertura:.0f}% dos dias úteis com registros")

    # 10. Destaque por score de produtividade
    if hasattr(kpis, 'score_produtividade') and kpis.score_produtividade:
        if kpis.score_produtividade >= 90:
            destaques.append(f"PRODUTIVIDADE EXCEPCIONAL - Score: {kpis.score_produtividade:.1f}")
        elif kpis.score_produtividade >= 80:
            destaques.append(f"ALTA PRODUTIVIDADE - Score: {kpis.score_produtividade:.1f}")

    # 11. Destaque por relação funcionários com registros
    if kpis.funcionarios_com_registos == kpis.total_funcionarios:
        destaques.append("ENGAJAMENTO TOTAL - 100% dos funcionários com registros no período")
    elif kpis.funcionarios_com_registos >= kpis.total_funcionarios * 0.9:  # 90% ou mais
        engajamento = (kpis.funcionarios_com_registos / kpis.total_funcionarios) * 100
        destaques.append(f"ALTO ENGAJAMENTO - {engajamento:.0f}% dos funcionários com registros")

    # Limitar a 5 destaques principais para não sobrecarregar
    if len(destaques) > 5:
        # Priorizar destaques por ordem de importância
        ordem_importancia = [
            'PERFEITO', 'EXCEPCIONAL', 'EXCELENTE', '100%', 'IDEAL',
            'CONSISTÊNCIA PERFEITA', 'COBERTURA COMPLETA', 'ENGAJAMENTO TOTAL'
        ]

        destaques_priorizados = []
        for palavra_chave in ordem_importancia:
            for destaque in destaques:
                if palavra_chave in destaque and destaque not in destaques_priorizados:
                    destaques_priorizados.append(destaque)
                    if len(destaques_priorizados) >= 5:
                        break
            if len(destaques_priorizados) >= 5:
                break

        # Se ainda não tiver 5, completar com os restantes
        if len(destaques_priorizados) < 5:
            for destaque in destaques:
                if destaque not in destaques_priorizados:
                    destaques_priorizados.append(destaque)
                    if len(destaques_priorizados) >= 5:
                        break

        return destaques_priorizados

    return destaques



def e_feriado(data: date) -> bool:
    """
    Verifica se uma data é feriado.
    Implementação básica - pode ser estendida para buscar de banco de dados.
    """
    # Feriados nacionais fixos no Brasil (exemplo)
    feriados_fixos = [
        (1, 1),  # Ano Novo
        (4, 21),  # Tiradentes
        (5, 1),  # Dia do Trabalho
        (9, 7),  # Independência
        (10, 12),  # Nossa Senhora Aparecida
        (11, 2),  # Finados
        (11, 15),  # Proclamação da República
        (12, 25),  # Natal
    ]

    return (data.month, data.day) in feriados_fixos


def get_avatar_url(user):
    """
    Retorna URL do avatar do usuário.
    """
    if hasattr(user, 'avatar') and user.avatar:
        return user.avatar.url
    elif hasattr(user, 'image') and user.image:
        return user.image.url
    else:
        # URL de avatar padrão
        return f"/static/avatars/default_{user.id % 5 + 1}.png"


def get_atividades_disponiveis():
    """
    Retorna atividades disponíveis para filtro.
    """
    from core.timesheet.models import Activity

    atividades = Activity.objects.filter(is_active=True).values('id', 'name').order_by('name')
    return [{"id": a['id'], "nome": a['name']} for a in atividades]


def gerar_acoes_recomendadas(kpis: KPIDepartamentoSchema,
                             indicadores_risco: List[IndicadorRiscoSchema],
                             alertas: List[AlertaSistemaSchema]) -> List[AcaoRecomendadaSchema]:
    """
    Gera ações recomendadas baseadas nos dados do dashboard.
    """
    acoes = []

    # Ação 1: Se taxa de utilização baixa
    if kpis.taxa_utilizacao < 60:
        acoes.append(
            AcaoRecomendadaSchema(
                id="acao_1",
                prioridade="media",
                categoria="gestao_pessoas",
                titulo="Melhorar Taxa de Utilização",
                descricao=f"Atualmente em {kpis.taxa_utilizacao:.1f}% - abaixo do ideal (70%+)",
                justificativa="Baixa utilização indica subutilização de recursos ou falta de projetos",
                passos=[
                    "Analisar distribuição atual de tarefas",
                    "Identificar projetos com capacidade ociosa",
                    "Reunir com equipe para alinhar expectativas",
                    "Propor novos projetos ou realocações"
                ],
                impacto_esperado="Aumento de 10-20% na utilização em 30 dias",
                esforco_estimado="medio",
                prazo_sugerido=(timezone.now() + timedelta(days=14)).date(),
                url_relacionada="/dashboard/analise/utilizacao"
            )
        )

    # Ação 2: Se taxa de submissão baixa
    if kpis.taxa_submissao < 80:
        acoes.append(
            AcaoRecomendadaSchema(
                id="acao_2",
                prioridade="alta",
                categoria="processos",
                titulo="Otimizar Submissão de Timesheets",
                descricao=f"Taxa atual: {kpis.taxa_submissao:.1f}% - alvo: 95%+",
                justificativa="Timesheets pendentes afetam faturamento e análise de dados",
                passos=[
                    "Identificar colaboradores com mais pendências",
                    "Implementar lembretes automáticos",
                    "Oferecer treinamento sobre o sistema",
                    "Simplificar processo de submissão"
                ],
                impacto_esperado="Redução de 50% em timesheets pendentes",
                esforco_estimado="baixo",
                prazo_sugerido=(timezone.now() + timedelta(days=7)).date(),
                url_relacionada="/timesheets/pendentes"
            )
        )

    # Ação 3: Se muitos dias sem registros
    if kpis.dias_sem_registos > 3:
        acoes.append(
            AcaoRecomendadaSchema(
                id="acao_3",
                prioridade="baixa",
                categoria="relatorios",
                titulo="Monitorar Dias sem Registros",
                descricao=f"{kpis.dias_sem_registos} dias úteis sem registros no período",
                justificativa="Dias sem registros podem indicar problemas de processo ou comunicação",
                passos=[
                    "Auditar processos de registro diário",
                    "Implementar checklist de final de dia",
                    "Criar relatório semanal de conformidade",
                    "Estabelecer metas de registro contínuo"
                ],
                impacto_esperado="Redução para 1-2 dias sem registros por mês",
                esforco_estimado="medio",
                prazo_sugerido=(timezone.now() + timedelta(days=21)).date(),
                url_relacionada="/dashboard/relatorios/conformidade"
            )
        )

    # Ação baseada em indicadores de risco
    for indicador in indicadores_risco[:2]:  # Limitar a 2 ações por indicadores
        if indicador.severidade == "alta":
            acoes.append(
                AcaoRecomendadaSchema(
                    id=f"risco_{indicador.tipo}",
                    prioridade="alta",
                    categoria="gestao_pessoas",
                    titulo=f"Mitigar {indicador.titulo}",
                    descricao=indicador.descricao,
                    justificativa=f"{indicador.quantidade_afetados} membros afetados",
                    passos=[
                        f"Analisar causa raiz do {indicador.tipo}",
                        "Elaborar plano de ação específico",
                        "Implementar medidas corretivas",
                        "Monitorar resultados semanalmente"
                    ],
                    impacto_esperado="Redução de 80% no indicador de risco",
                    esforco_estimado="alto",
                    prazo_sugerido=(timezone.now() + timedelta(days=10)).date(),
                    url_relacionada=f"/dashboard/riscos/{indicador.tipo}"
                )
            )

    return acoes


def identificar_destaques(kpis: KPIDepartamentoSchema, top_funcionarios: List[Dict]) -> List[str]:
    """
    Identifica destaques positivos no dashboard.
    """
    destaques = []

    if kpis.taxa_submissao > 95:
        destaques.append(f"Excelente taxa de submissão: {kpis.taxa_submissao:.1f}%")

    if kpis.score_eficiencia > 80:
        destaques.append(f"Alta eficiência organizacional: {kpis.score_eficiencia:.1f}")

    if kpis.dias_sem_registos == 0:
        destaques.append("Registro diário consistente - nenhum dia sem registros")

    if top_funcionarios:
        melhor_funcionario = max(top_funcionarios, key=lambda x: x.get('total_horas', 0))
        horas = melhor_funcionario.get('total_horas', 0)
        nome = melhor_funcionario.get('funcionario', {}).get('nome_completo', '')
        if horas > 0:
            destaques.append(f"{nome}: {horas:.1f}h (maior produtividade)")

    return destaques


def identificar_pontos_atencao(kpis: KPIDepartamentoSchema, indicadores_risco: List[IndicadorRiscoSchema]) -> List[str]:
    """
    Identifica pontos que precisam de atenção.
    """
    pontos = []

    if kpis.taxa_utilizacao < 60:
        pontos.append(f"Baixa utilização: {kpis.taxa_utilizacao:.1f}% (meta: 70%+)")

    if kpis.taxa_submissao < 80:
        pontos.append(f"Submissão abaixo do esperado: {kpis.taxa_submissao:.1f}%")

    if kpis.dias_sem_registos > kpis.dias_uteis * 0.1:  # >10%
        pontos.append(f"Muitos dias sem registros: {kpis.dias_sem_registos} de {kpis.dias_uteis}")

    if kpis.score_eficiencia < 70:
        pontos.append(f"Eficiência abaixo do ideal: {kpis.score_eficiencia:.1f}")

    for indicador in indicadores_risco[:3]:  # Limitar a 3
        pontos.append(f"{indicador.titulo}: {indicador.descricao}")

    return pontos


def calcular_completude_dados(membros, inicio: date, fim: date) -> float:
    """
    Calcula completude dos dados no período.
    """
    total_dias_uteis = calcular_dias_uteis(inicio, fim)
    total_possivel = len(membros) * total_dias_uteis

    if total_possivel == 0:
        return 0.0

    # Contar dias com registros
    dias_com_registros = Task.objects.filter(
        timesheet__employee__in=membros,
        created_at__range=[inicio, fim]
    ).values('created_at__date').distinct().count()

    return (dias_com_registros / total_possivel) * 100


def get_timesheets_recentes(departamento: Department, limite: int = 10) -> List[Dict]:
    """
    Retorna timesheets recentes do departamento.
    """
    membros = get_department_members(departamento, only_active=True)

    timesheets = Timesheet.objects.filter(
        employee__in=membros
    ).select_related('employee').order_by('-created_at')[:limite]

    return [
        {
            "id": ts.id,
            "funcionario": ts.employee.get_full_name(),
            "data": ts.created_at.date(),
            "status": ts.status,
            "horas_totais": ts.tasks.aggregate(total=Sum('hour'))['total'] or 0,
            "projetos": ts.tasks.values('project__name').distinct().count()
        }
        for ts in timesheets
    ]


def get_tarefas_recentes(departamento: Department, limite: int = 10) -> List[Dict]:
    """
    Retorna tarefas recentes do departamento.
    """
    membros = get_department_members(departamento, only_active=True)

    tarefas = Task.objects.filter(
        timesheet__employee__in=membros
    ).select_related('timesheet__employee', 'project').order_by('-created_at')[:limite]

    return [
        {
            "id": t.id,
            "descricao": t.description,
            "funcionario": t.timesheet.employee.get_full_name(),
            "projeto": t.project.name if t.project else "Sem projeto",
            "horas": t.hour,
            "data": t.created_at.date(),
            "atividade": t.activity.name if t.activity else "Sem atividade"
        }
        for t in tarefas
    ]


def get_aprovacoes_recentes(departamento: Department, limite: int = 5) -> List[Dict]:
    """
    Retorna aprovações recentes (se aplicável).
    """
    # Implementar conforme seu modelo de aprovações
    return []


def get_comentarios_recentes(departamento: Department, limite: int = 5) -> List[Dict]:
    """
    Retorna comentários recentes (se aplicável).
    """
    # Implementar conforme seu modelo de comentários
    return []


def calcular_kpis_funcionario(funcionario: User, periodo_inicio: date, periodo_fim: date) -> Dict[str, Any]:
    """
    Calcula KPIs específicos de um funcionário.
    """
    tarefas = Task.objects.filter(
        timesheet__employee=funcionario,
        created_at__range=[periodo_inicio, periodo_fim]
    )

    horas_total = tarefas.aggregate(total=Sum('hour'))['total'] or Decimal('0.00')
    dias_trabalhados = tarefas.values('created_at__date').distinct().count()
    media_horas_diaria = float(horas_total) / dias_trabalhados if dias_trabalhados > 0 else 0

    timesheets = Timesheet.objects.filter(
        employee=funcionario,
        created_at__range=[periodo_inicio, periodo_fim]
    )

    total_ts = timesheets.count()
    submetidos = timesheets.filter(status='submetido').count()
    taxa_submissao = (submetidos / total_ts * 100) if total_ts > 0 else 0

    aprovados = timesheets.filter(status='aprovado').count()
    taxa_aprovacao = (aprovados / total_ts * 100) if total_ts > 0 else None

    projetos_trabalhados = tarefas.values('project').distinct().count()

    top_projeto = tarefas.values(
        'project_id', 'project__name'
    ).annotate(
        horas=Sum('hour')
    ).order_by('-horas').first()

    top_projeto_info = None
    if top_projeto:
        top_projeto_info = {
            "id": top_projeto['project_id'],
            "nome": top_projeto['project__name'],
            "horas": float(top_projeto['horas'] or 0)
        }

    return {
        "total_horas": horas_total,
        "dias_trabalhados": dias_trabalhados,
        "media_horas_diaria": media_horas_diaria,
        "taxa_submissao": taxa_submissao,
        "taxa_aprovacao": taxa_aprovacao,
        "projetos_trabalhados": projetos_trabalhados,
        "top_projeto": top_projeto_info,
        "horas_extras": Decimal('0.00'),
        "horas_fim_semana": Decimal('0.00')
    }


def calcular_ranking_funcionario(funcionario: User, departamento: Department,
                                 periodo_inicio: date, periodo_fim: date) -> Dict[str, Any]:
    """
    Calcula ranking do funcionário no departamento.
    """
    membros = get_department_members(departamento, only_active=True)

    # Calcular horas de todos os membros
    ranking = []
    for membro in membros:
        horas = Task.objects.filter(
            timesheet__employee=membro,
            created_at__range=[periodo_inicio, periodo_fim]
        ).aggregate(total=Sum('hour'))['total'] or Decimal('0.00')

        ranking.append({
            "id": membro.id,
            "nome": membro.get_full_name(),
            "horas": float(horas)
        })

    # Ordenar por horas
    ranking.sort(key=lambda x: x['horas'], reverse=True)

    # Encontrar posição do funcionário
    posicao = 1
    for i, item in enumerate(ranking):
        if item['id'] == funcionario.id:
            posicao = i + 1
            break

    total_membros = len(ranking)
    percentil = ((total_membros - posicao) / total_membros) * 100 if total_membros > 0 else 0

    return {
        "posicao": posicao,
        "total_membros": total_membros,
        "percentil": round(percentil, 1),
        "top_3": ranking[:3]
    }

# ==================== FUNÇÕES AUXILIARES REUTILIZÁVEIS ====================


def calcular_distribuicao_projetos(
        departamento: Department,
        periodo_inicio: date,
        periodo_fim: date,
        membros
) -> List[DistribuicaoProjetoSchema]:
    """
    Calcula distribuição de horas por projeto
    """
    # Agrupar tasks por projeto
    projetos_data = Task.objects.filter(
        timesheet__employee__in=membros,
        created_at__range=[periodo_inicio, periodo_fim]
    ).exclude(
        Q(project__isnull=True) | Q(project__name__isnull=True)
    ).values(
        'project_id',
        'project__name',
        'project__code',
        'project__client__name'
    ).annotate(
        total_horas=Sum('hour'),
        funcionarios_envolvidos=Count('timesheet__employee', distinct=True)
    ).order_by('-total_horas')

    # Calcular horas totais para percentuais
    horas_totais = sum(item['total_horas'] or Decimal('0.00') for item in projetos_data)

    distribucao = []
    for item in projetos_data:
        horas = item['total_horas'] or Decimal('0.00')
        percentual = (float(horas) / float(horas_totais) * 100) if horas_totais > 0 else 0

        # Obter informações do projeto
        projeto = {
            "id": item['project_id'],
            "nome": item['project__name'],
            "codigo": item['project__code'],
            "cliente": item['project__client__name'],
            "horas_executadas": horas,
            "horas_orcadas": None,  # Se tiver no seu modelo
            "percentual_conclusao": None,  # Se tiver no seu modelo
            "data_inicio": None,
            "data_fim": None
        }

        distribucao.append(
            DistribuicaoProjetoSchema(
                projeto=projeto,
                total_horas=horas,
                percentual=percentual,
                funcionarios_envolvidos=item['funcionarios_envolvidos'],
                media_horas_funcionario=(
                    float(horas) / item['funcionarios_envolvidos']
                    if item['funcionarios_envolvidos'] > 0 else 0
                ),
                percentual_conclusao=calcular_percentual_conclusao(item['project_id'])
            )
        )

    return distribucao


def calcular_evolucao_diaria(
        departamento: Department,
        periodo_inicio: date,
        periodo_fim: date,
        membros
) -> List[EvolucaoDiariaSchema]:
    """
    Calcula evolução das horas por dia
    """
    # Agrupar por dia
    daily_data = Task.objects.filter(
        timesheet__employee__in=membros,
        created_at__range=[periodo_inicio, periodo_fim]
    ).values('created_at__date').annotate(
        total_horas=Sum('hour'),
        funcionarios_atividades=Count('timesheet__employee', distinct=True),
        projetos_atividades=Count('project', distinct=True)
    ).order_by('created_at__date')

    evolucao = []
    for item in daily_data:
        data = item['created_at__date']
        total_horas = item['total_horas'] or Decimal('0.00')
        funcionarios = item['funcionarios_atividades']

        evolucao.append(
            EvolucaoDiariaSchema(
                data=data,
                total_horas=total_horas,
                funcionarios_atividades=funcionarios,
                projetos_atividades=item['projetos_atividades'],
                media_horas_funcionario=(
                    float(total_horas) / funcionarios if funcionarios > 0 else 0
                ),
                dia_semana=data.strftime('%A'),
                e_feriado=e_feriado(data),
                e_fim_semana=data.weekday() >= 5  # Sábado=5, Domingo=6
            )
        )

    return evolucao


def gerar_alertas_departamento(
        departamento: Department,
        periodo_inicio: date,
        periodo_fim: date,
        kpis: KPIDepartamentoSchema
) -> List[AlertaSistemaSchema]:
    """
    Gera alertas proativos para o departamento
    """
    alertas = []
    alert_id = 1

    # 1. Alerta de baixa utilização
    if kpis.taxa_utilizacao < 60:
        alertas.append(
            AlertaSistemaSchema(
                id=f"alert_{alert_id}",
                tipo="aviso",
                titulo="Baixa Taxa de Utilização",
                descricao=f"Taxa de utilização de {kpis.taxa_utilizacao:.1f}% está abaixo do ideal (70%+)",
                prioridade="media",
                data_criacao=timezone.now(),
                data_expiracao=timezone.now() + timedelta(days=7),
                acao_requerida=True,
                url_acao=f"/dashboard/gestor/{departamento.id}/analise",
                lido=False
            )
        )
        alert_id += 1

    # 2. Alerta de baixa submissão
    if kpis.taxa_submissao < 80:
        alertas.append(
            AlertaSistemaSchema(
                id=f"alert_{alert_id}",
                tipo="critico",
                titulo="Baixa Taxa de Submissão",
                descricao=f"Apenas {kpis.taxa_submissao:.1f}% dos timesheets foram submetidos",
                prioridade="alta",
                data_criacao=timezone.now(),
                data_expiracao=timezone.now() + timedelta(days=3),
                acao_requerida=True,
                url_acao=f"/dashboard/timesheets/pendentes",
                lido=False
            )
        )
        alert_id += 1

    # 3. Alerta de muitos dias sem registros
    if kpis.dias_sem_registos > kpis.dias_uteis * 0.3:  # >30%
        alertas.append(
            AlertaSistemaSchema(
                id=f"alert_{alert_id}",
                tipo="informacao",
                titulo="Muitos Dias sem Registros",
                descricao=f"{kpis.dias_sem_registos} dias úteis sem registros de horas",
                prioridade="baixa",
                data_criacao=timezone.now(),
                acao_requerida=False,
                lido=False
            )
        )
        alert_id += 1

    return alertas


def identificar_indicadores_risco(
        departamento: Department,
        kpis: KPIDepartamentoSchema,
        distribucao_projetos: List[DistribuicaoProjetoSchema]
) -> List[IndicadorRiscoSchema]:
    """
    Identifica indicadores de risco no departamento
    """
    indicadores = []
    membros = get_department_members(departamento, only_active=True)
    membros_nomes = [m.get_full_name() for m in membros[:5]]  # Limitar a 5 nomes

    # 1. Risco de sobrecarga
    if kpis.media_horas_diaria > 10:
        indicadores.append(
            IndicadorRiscoSchema(
                tipo="sobrecarga",
                severidade="media",
                titulo="Possível Sobrecarga de Trabalho",
                descricao=f"Média diária de {kpis.media_horas_diaria:.1f} horas por funcionário",
                funcionarios_afetados=membros_nomes,
                quantidade_afetados=len(membros_nomes),
                acao_sugerida="Revisar distribuição de tarefas",
                data_deteccao=timezone.now()
            )
        )

    # 2. Risco de subutilização
    if kpis.taxa_utilizacao < 50:
        indicadores.append(
            IndicadorRiscoSchema(
                tipo="subutilizacao",
                severidade="alta",
                titulo="Subutilização de Recursos",
                descricao=f"Apenas {kpis.taxa_utilizacao:.1f}% da capacidade está sendo utilizada",
                funcionarios_afetados=membros_nomes,
                quantidade_afetados=len(membros_nomes),
                acao_sugerida="Analisar novos projetos ou redistribuir equipe",
                data_deteccao=timezone.now()
            )
        )

    # 3. Risco de concentração em poucos projetos
    if distribucao_projetos and len(distribucao_projetos) > 0:
        top_projeto_percent = distribucao_projetos[0].percentual
        if top_projeto_percent > 60:  # Mais de 60% em um só projeto
            indicadores.append(
                IndicadorRiscoSchema(
                    tipo="concentracao_projetos",
                    severidade="media",
                    titulo="Alta Concentração em um Projeto",
                    descricao=f"{top_projeto_percent:.1f}% das horas em um único projeto",
                    funcionarios_afetados=membros_nomes,
                    quantidade_afetados=len(membros_nomes),
                    acao_sugerida="Diversificar alocação para reduzir dependência",
                    data_deteccao=timezone.now()
                )
            )

    return indicadores

"""
Funções utilitárias estendidas para suportar modo direção
"""

from core.timesheet.models import Task, Timesheet, User
from core.user.models import Department
from datetime import date, timedelta
from decimal import Decimal
from django.db.models import Sum, Count, Q, F
from django.utils import timezone


def get_department_metrics_extended(department, start_date, end_date):
    """
    Versão estendida da função de métricas do departamento
    """
    # Reutilizar função existente se disponível
    try:
        from .util import calculate_department_metrics
        return calculate_department_metrics(department, start_date, end_date)
    except ImportError:
        # Implementação alternativa
        return calculate_department_metrics_fallback(department, start_date, end_date)


def calculate_department_metrics_fallback(department, start_date, end_date):
    """
    Implementação fallback das métricas do departamento
    """
    # Obter membros
    members = department.users.filter(is_active=True)

    # Calcular totais
    tasks = Task.objects.filter(
        timesheet__employee__in=members,
        created_at__range=[start_date, end_date]
    )

    total_hours = tasks.aggregate(total=Sum('hour'))['total'] or Decimal('0.00')
    total_members = members.count()
    days_in_period = (end_date - start_date).days + 1

    # Taxa de submissão
    timesheets = Timesheet.objects.filter(
        employee__in=members,
        created_at__range=[start_date, end_date]
    )

    submission_stats = timesheets.aggregate(
        total=Count('id'),
        submitted=Count('id', filter=Q(status='submetido'))
    )

    submission_rate = 0
    if submission_stats['total'] > 0:
        submission_rate = (submission_stats['submitted'] / submission_stats['total']) * 100

    # Distribuição por projeto
    project_distribution = tasks.values(
        'project__name'
    ).annotate(
        total_hours=Sum('hour'),
        member_count=Count('timesheet__employee', distinct=True)
    ).order_by('-total_hours')

    # Calcular eficiência (exemplo simplificado)
    efficiency_score = calculate_efficiency_score(
        total_hours=total_hours,
        total_members=total_members,
        days_in_period=days_in_period,
        submission_rate=submission_rate
    )

    return {
        "summary": {
            "total_members": total_members,
            "active_members": members.filter(is_active=True).count(),
            "total_hours": total_hours,
            "avg_hours_per_member": float(total_hours) / total_members if total_members > 0 else 0,
            "avg_hours_per_day": float(total_hours) / days_in_period if days_in_period > 0 else 0,
            "utilization_rate": calculate_utilization_rate_fallback(total_hours, total_members, days_in_period),
            "total_projects": project_distribution.count(),
            "submission_rate": round(submission_rate, 1),
            "approval_rate": None,
            "avg_days_to_submit": None
        },
        "project_distribution": [
            {
                "project_name": item['project__name'] or "Sem projeto",
                "total_hours": item['total_hours'],
                "member_count": item['member_count'],
                "percentage": (float(item['total_hours']) / float(total_hours) * 100) if total_hours > 0 else 0
            }
            for item in project_distribution
        ],
        "risk_indicators": [],
        "efficiency_score": efficiency_score
    }


def calculate_efficiency_score(total_hours, total_members, days_in_period, submission_rate):
    """
    Calcula score de eficiência (0-100)
    """
    # Fator de horas (0-50 pontos)
    target_hours_per_day = 8
    target_total_hours = total_members * days_in_period * target_hours_per_day

    if target_total_hours > 0:
        hours_factor = min(50, (float(total_hours) / target_total_hours) * 50)
    else:
        hours_factor = 0

    # Fator de submissão (0-50 pontos)
    submission_factor = (submission_rate / 100) * 50

    return round(hours_factor + submission_factor, 1)


def calculate_utilization_rate_fallback(total_hours, total_members, days_in_period):
    """
    Calcula taxa de utilização (0-100%)
    """
    if total_members == 0 or days_in_period == 0:
        return 0

    # Horas teóricas máximas (8 horas por dia)
    max_possible_hours = total_members * days_in_period * 8

    if max_possible_hours > 0:
        utilization = (float(total_hours) / max_possible_hours) * 100
        return round(min(utilization, 100), 1)

    return 0


def get_department_manager_fallback(department):
    """
    Obtém gestor do departamento (fallback)
    """
    # Tentar várias abordagens
    if hasattr(department, 'manager') and department.manager:
        return department.manager

    # Buscar por grupos
    from django.contrib.auth.models import Group
    try:
        manager_group = Group.objects.get(name="Gestores")
        return department.users.filter(groups=manager_group).first()
    except:
        pass

    # Buscar por permissão
    from django.contrib.auth.models import Permission
    from django.contrib.contenttypes.models import ContentType

    try:
        content_type = ContentType.objects.get_for_model(Department)
        permission = Permission.objects.get(
            codename='change_department',
            content_type=content_type
        )
        return department.users.filter(
            Q(user_permissions=permission) |
            Q(groups__permissions=permission)
        ).first()
    except:
        pass

    return None



def calcular_taxa_utilizacao(departamento_id: int, data_inicio: date, data_fim: date) -> float:
    """
    Calcula taxa de utilização do departamento
    """
    # Horas trabalhadas
    horas_trabalhadas = Timesheet.objects.filter(
        department_id=departamento_id,
        created_at__range=[data_inicio, data_fim],
        status='submetido'
    ).aggregate(total=Sum('total_hour'))['total'] or Decimal('0.00')

    # Funcionários ativos
    funcionarios_ativos = User.objects.filter(
        department_id=departamento_id,
        is_active=True
    ).count()

    # Dias úteis no período
    dias_uteis = _calcular_dias_uteis(data_inicio, data_fim)

    # Horas possíveis (8h por dia por funcionário)
    horas_possiveis = funcionarios_ativos * dias_uteis * 8

    # Taxa de utilização
    taxa = (float(horas_trabalhadas) / horas_possiveis * 100) if horas_possiveis > 0 else 0

    return min(taxa, 100)  # Limitar a 100%


def _calcular_dias_uteis(data_inicio: date, data_fim: date) -> int:
    """Calcula dias úteis entre duas datas"""
    dias = 0
    current = data_inicio

    while current <= data_fim:
        if current.weekday() < 5:  # Segunda a Sexta
            dias += 1
        current += timedelta(days=1)

    return dias


def identificar_riscos(departamento_id: int, periodo_dias: int = 7):
    """
    Identifica riscos potenciais no departamento
    """
    riscos = []
    data_limite = timezone.now().date() - timedelta(days=periodo_dias)

    # 1. Funcionários sobrecarregados (>10h/dia em média)
    sobrecarregados = Timesheet.objects.filter(
        department_id=departamento_id,
        created_at__gte=data_limite
    ).values('employee').annotate(
        total_horas=Sum('total_hour'),
        dias_trabalhados=Count('created_at', distinct=True)
    ).filter(
        dias_trabalhados__gt=0
    ).annotate(
        media_diaria=F('total_horas') / F('dias_trabalhados')
    ).filter(
        media_diaria__gt=10
    )

    if sobrecarregados.exists():
        riscos.append({
            "tipo": "sobrecarga",
            "severidade": "alta",
            "descricao": f"{sobrecarregados.count()} funcionários com média >10h/dia",
            "detalhes": list(sobrecarregados.values('employee', 'media_diaria'))
        })

    # 2. Projetos sem horas
    projetos_sem_horas = Task.objects.filter(
        timesheet__department_id=departamento_id,
        created_at__gte=data_limite
    ).values('project').annotate(
        total_horas=Sum('hour')
    ).filter(
        total_horas__lte=1
    )

    if projetos_sem_horas.exists():
        riscos.append({
            "tipo": "projetos_sem_horas",
            "severidade": "media",
            "descricao": f"{projetos_sem_horas.count()} projetos com poucas horas",
            "detalhes": list(projetos_sem_horas.values('project', 'total_horas'))
        })

    return riscos


def gerar_insights(departamento_id: int, data_inicio: date, data_fim: date):
    """
    Gera insights automáticos baseados nos dados
    """
    insights = []

    # Horas por dia da semana
    horas_por_dia = Timesheet.objects.filter(
        department_id=departamento_id,
        created_at__range=[data_inicio, data_fim]
    ).extra({
        'day_of_week': "EXTRACT(dow FROM created_at)"
    }).values('day_of_week').annotate(
        total_horas=Sum('total_hour')
    ).order_by('day_of_week')

    # Identificar dias com menor produtividade
    dias_semana = ['Dom', 'Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sab']
    for dia in horas_por_dia:
        if dia['total_horas'] and dia['total_horas'] < 20:  # Limite arbitrário
            insights.append(
                f"Baixa produtividade nas {dias_semana[int(dia['day_of_week'])]}s"
            )

    # Distribuição de horas
    total_horas = Timesheet.objects.filter(
        department_id=departamento_id,
        created_at__range=[data_inicio, data_fim]
    ).aggregate(total=Sum('total_hour'))['total'] or Decimal('0.00')

    if total_horas > 0:
        # Top 3 funcionários concentram mais de 50% das horas?
        top3_funcionarios = Timesheet.objects.filter(
            department_id=departamento_id,
            created_at__range=[data_inicio, data_fim]
        ).values('employee').annotate(
            total_horas=Sum('total_hour')
        ).order_by('-total_horas')[:3]

        horas_top3 = sum([f['total_horas'] for f in top3_funcionarios if f['total_horas']])
        percentual_top3 = (float(horas_top3) / float(total_horas)) * 100

        if percentual_top3 > 50:
            insights.append(
                f"Concentração de horas: top 3 funcionários realizam {percentual_top3:.1f}% das horas"
            )

    return insights