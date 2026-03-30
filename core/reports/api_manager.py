from django.core.exceptions import PermissionDenied
from ninja import Router, Query
from django.db.models import Q, Sum, Count
from django.db.models import DecimalField
from datetime import timedelta
from django.utils import timezone
from typing import List, Optional, Dict, Any
from decimal import Decimal
from datetime import date
from core.login.jwt_auth import JWTAuth

from .schemas_manager import (
    ManagerDashboardResponseSchema,
    ManagerFilterSchema,
    ManagerFilterOptionsSchema,
    DepartmentSchema,
    BasicEmployeeSchema,
    ProjectSchema,
    DepartmentKPISchema,
    EmployeeKPISchema,
    ProjectDistributionSchema,
    RoleDistributionSchema,
    DailyEvolutionSchema,
    SystemAlertSchema,
    PeriodEnum,
    TimesheetStatusEnum,
    AggregationLevelEnum,
    SeverityEnum
)
from core.timesheet.models import Task, Timesheet
from core.user.models import User
from core.activity.models import Activity

router = Router(tags=["Manager Dashboard"], auth=JWTAuth())

# ==================== HELPERS ====================
def check_manager_access(request, department):
    """Verifica se o utilizador é administrador ou o gestor do departamento."""
    user = request.auth
    if user.is_administrator:
        return True
    if department.manager_id == user.id:
        return True
    
    # Adicionalmente, verificar se o utilizador é um gestor delegado (deputy manager)
    if hasattr(department, 'deputy_managers') and department.deputy_managers.filter(id=user.id).exists():
        return True

    raise PermissionDenied("Você não tem permissão para aceder aos dados deste departamento.")

# ==================== CACHE CONFIGURATION ====================
from django.core.cache import cache

CACHE_TIMEOUT = 300  # 5 minutes
CACHE_KEY_PREFIX = "manager_dashboard_"


# ==================== HELPER FUNCTIONS ====================
def get_manager_department(request):
    """Get manager's department"""
    user = request.auth
    if not user or not user.is_authenticated:
        raise PermissionDenied("User not authenticated")

    if not user.department:
        raise PermissionDenied("Manager has no department assigned")

    return user.department


def get_department_employees(department, include_manager=False, only_active=True):
    """Get employees from department with filters"""
    queryset = User.objects.filter(department=department)

    # CORREÇÃO: Verificar se manager_id não é None
    if not include_manager and department.manager_id:
        queryset = queryset.exclude(id=department.manager_id)

    if only_active:
        queryset = queryset.filter(is_active=True)

    return queryset.select_related('position', 'department')


def get_period_date_range(period: PeriodEnum, start_date: Optional[date] = None, end_date: Optional[date] = None):
    """Get date range for period"""
    today = timezone.now().date()

    if period == PeriodEnum.TODAY:
        return {'start_date': today, 'end_date': today, 'label': 'Today'}
    elif period == PeriodEnum.YESTERDAY:
        yesterday = today - timedelta(days=1)
        return {'start_date': yesterday, 'end_date': yesterday, 'label': 'Yesterday'}
    elif period == PeriodEnum.WEEK:
        start = today - timedelta(days=today.weekday())
        return {'start_date': start, 'end_date': today, 'label': 'This Week'}
    elif period == PeriodEnum.LAST_WEEK:
        start = today - timedelta(days=today.weekday() + 7)
        end = start + timedelta(days=6)
        return {'start_date': start, 'end_date': end, 'label': 'Last Week'}
    elif period == PeriodEnum.MONTH:
        start = today.replace(day=1)
        return {'start_date': start, 'end_date': today, 'label': 'This Month'}
    elif period == PeriodEnum.LAST_MONTH:
        first_day_current = today.replace(day=1)
        last_day_previous = first_day_current - timedelta(days=1)
        start = last_day_previous.replace(day=1)
        return {'start_date': start, 'end_date': last_day_previous, 'label': 'Last Month'}
    elif period == PeriodEnum.QUARTER:
        quarter = (today.month - 1) // 3
        start_month = quarter * 3 + 1
        start = date(today.year, start_month, 1)
        return {'start_date': start, 'end_date': today, 'label': 'This Quarter'}
    elif period == PeriodEnum.YEAR:
        start = date(today.year, 1, 1)
        return {'start_date': start, 'end_date': today, 'label': 'This Year'}
    elif period == PeriodEnum.CUSTOM:
        if not start_date or not end_date:
            start_date = today.replace(day=1)
            end_date = today
        return {'start_date': start_date, 'end_date': end_date, 'label': f'{start_date} to {end_date}'}
    else:
        start = today.replace(day=1)
        return {'start_date': start, 'end_date': today, 'label': 'This Month'}


def calculate_department_kpis1(employees_ids, start_date, end_date, filters: ManagerFilterSchema):
    """Calculate department KPIs"""

    # Build filters for tasks
    tasks_filters = Q(
        timesheet__employee_id__in=employees_ids,
        created_at__gte=start_date,
        created_at__lte=end_date
    )

    if filters.project_id:
        tasks_filters &= Q(project_id=filters.project_id)
    if filters.activity_id:
        tasks_filters &= Q(activity_id=filters.activity_id)
    if filters.status:
        tasks_filters &= Q(timesheet__status=filters.status.value)

    tasks_qs = Task.objects.filter(tasks_filters)

    # Build filters for timesheets
    ts_filters = Q(
        employee_id__in=employees_ids,
        created_at__gte=start_date,
        created_at__lte=end_date
    )

    if filters.status:
        ts_filters &= Q(status=filters.status.value)

    timesheets_qs = Timesheet.objects.filter(ts_filters)

    # Calculate total hours
    total_hours_result = tasks_qs.aggregate(
        total=Sum('hour', output_field=DecimalField(max_digits=10, decimal_places=2))
    )
    total_hours = total_hours_result['total'] or Decimal('0.00')

    # Calculate days
    days_in_period = (end_date - start_date).days + 1
    workdays = days_in_period  # Simplified, should exclude weekends/holidays

    # Get unique days with records
    worked_days = tasks_qs.dates('created_at', 'day').distinct().count()
    days_without_records = workdays - worked_days

    # Calculate employee counts
    employees_with_records = tasks_qs.values('timesheet__employee').distinct().count()
    total_employees = len(employees_ids)

    # Calculate averages
    daily_average_hours = float(total_hours) / worked_days if worked_days > 0 else 0
    average_hours_per_employee = float(total_hours) / employees_with_records if employees_with_records > 0 else 0

    # Calculate submission rate
    total_timesheets = timesheets_qs.count()
    submitted_timesheets = timesheets_qs.filter(status=TimesheetStatusEnum.SUBMITTED.value).count()

    submission_rate = (submitted_timesheets / total_timesheets * 100) if total_timesheets > 0 else 0

    # Calculate utilization rate
    expected_hours = total_employees * workdays * 8  # 8 hours per day
    utilization_rate = (float(total_hours) / expected_hours * 100) if expected_hours > 0 else 0

    # Get project counts
    projects = tasks_qs.exclude(project__isnull=True).values('project').distinct()
    total_projects = projects.count()
    active_projects = total_projects

    # Calculate scores
    efficiency_score = min(utilization_rate * 1.2, 100)
    productivity_score = min((daily_average_hours / 8) * 100, 100)
    participation_rate = (employees_with_records / total_employees) * 100
    return {
        'total_hours': str(total_hours),  # Convert to string for Decimal serialization
        'daily_average_hours': daily_average_hours,
        'average_hours_per_employee': average_hours_per_employee,
        'utilization_rate': utilization_rate,
        'submission_rate': submission_rate,
        'approval_rate': None,
        'total_employees': total_employees,
        'employees_with_records': employees_with_records,
        'total_projects': total_projects,
        'active_projects': active_projects,
        'worked_days': worked_days,
        'workdays': workdays,
        'days_without_records': days_without_records,
        'efficiency_score': efficiency_score,
        'productivity_score': productivity_score,
        'participation_rate': participation_rate
    }


def calculate_department_kpis(employees_ids, start_date, end_date, filters: ManagerFilterSchema):
    """Calculate department KPIs"""

    # Build filters for tasks
    tasks_filters = Q(
        timesheet__employee_id__in=employees_ids,
        created_at__gte=start_date,
        created_at__lte=end_date
    )

    if filters.project_id:
        tasks_filters &= Q(project_id=filters.project_id)
    if filters.activity_id:
        tasks_filters &= Q(activity_id=filters.activity_id)
    if filters.status:
        tasks_filters &= Q(timesheet__status=filters.status.value)

    tasks_qs = Task.objects.filter(tasks_filters)

    # Build filters for timesheets
    ts_filters = Q(
        employee_id__in=employees_ids,
        created_at__gte=start_date,
        created_at__lte=end_date
    )

    if filters.status:
        ts_filters &= Q(status=filters.status.value)

    timesheets_qs = Timesheet.objects.filter(ts_filters)

    # Calculate total hours
    total_hours_result = tasks_qs.aggregate(
        total=Sum('hour', output_field=DecimalField(max_digits=10, decimal_places=2))
    )
    total_hours = total_hours_result['total'] or Decimal('0.00')

    # Calculate days
    days_in_period = (end_date - start_date).days + 1
    workdays = days_in_period  # Simplified, should exclude weekends/holidays

    # Get unique days with records
    worked_days = tasks_qs.dates('created_at', 'day').distinct().count()
    days_without_records = workdays - worked_days

    # Calculate employee counts
    employees_with_records = tasks_qs.values('timesheet__employee').distinct().count()
    total_employees = len(employees_ids)

    # CORRIGIDO: Média diária baseada no TOTAL de dias no período
    daily_average_hours = float(total_hours) / days_in_period if days_in_period > 0 else 0

    # Mantido para cálculos a nível de funcionário
    average_hours_per_employee = float(total_hours) / employees_with_records if employees_with_records > 0 else 0

    # Calculate submission rate
    total_timesheets = timesheets_qs.count()
    submitted_timesheets = timesheets_qs.filter(status=TimesheetStatusEnum.SUBMITTED.value).count()
    submission_rate = (submitted_timesheets / total_timesheets * 100) if total_timesheets > 0 else 0

    # Calculate utilization rate
    expected_hours = total_employees * workdays * 8  # 8 hours per day
    utilization_rate = (float(total_hours) / expected_hours * 100) if expected_hours > 0 else 0

    # Get project counts
    projects = tasks_qs.exclude(project__isnull=True).values('project').distinct()
    total_projects = projects.count()
    active_projects = total_projects

    # Calculate scores
    efficiency_score = min(utilization_rate * 1.2, 100)
    productivity_score = min((daily_average_hours / 8) * 100, 100)
    participation_rate = (employees_with_records / total_employees) * 100 if total_employees > 0 else 0

    return {
        'total_hours': str(total_hours),
        'daily_average_hours': daily_average_hours,  # AGORA: total_horas / total_dias_no_periodo
        'average_hours_per_employee': average_hours_per_employee,  # total_horas / funcionarios_com_registros
        'utilization_rate': utilization_rate,
        'submission_rate': submission_rate,
        'approval_rate': None,
        'total_employees': total_employees,
        'employees_with_records': employees_with_records,
        'total_projects': total_projects,
        'active_projects': active_projects,
        'worked_days': worked_days,
        'workdays': workdays,
        'days_without_records': days_without_records,
        'efficiency_score': efficiency_score,
        'productivity_score': productivity_score,
        'participation_rate': participation_rate
    }

def get_project_distribution(employees_ids, start_date, end_date, filters: ManagerFilterSchema,
                             limit: Optional[int] = None):
    """Get hour distribution by project"""

    tasks_filters = Q(
        timesheet__employee_id__in=employees_ids,
        created_at__gte=start_date,
        created_at__lte=end_date
    )

    if filters.activity_id:
        tasks_filters &= Q(activity_id=filters.activity_id)
    if filters.status:
        tasks_filters &= Q(timesheet__status=filters.status.value)

    # Get total hours for percentage calculation
    total_hours_qs = Task.objects.filter(tasks_filters)
    total_hours_result = total_hours_qs.aggregate(
        total=Sum('hour', output_field=DecimalField(max_digits=10, decimal_places=2))
    )
    total_department_hours = total_hours_result['total'] or Decimal('0.00')

    # Get project distribution
    project_stats = Task.objects.filter(tasks_filters).exclude(project__isnull=True).values(
        'project_id', 'project__name'
    ).annotate(
        total_hours=Sum('hour'),
        employees_involved=Count('timesheet__employee', distinct=True)
    ).order_by('-total_hours')

    # Apply limit if provided
    if limit:
        project_stats = project_stats[:limit]

    distribution = []
    for proj in project_stats:
        percentage = (float(proj['total_hours']) / float(
            total_department_hours) * 100) if total_department_hours > 0 else 0
        avg_hours = float(proj['total_hours']) / proj['employees_involved'] if proj['employees_involved'] > 0 else 0

        project_schema = ProjectSchema(
            id=proj['project_id'],
            name=proj['project__name'],
            actual_hours=str(proj['total_hours'])
        )

        distribution.append(ProjectDistributionSchema(
            project=project_schema,
            total_hours=str(proj['total_hours']),
            percentage=percentage,
            employees_involved=proj['employees_involved'],
            average_hours_per_employee=avg_hours
        ))

    return distribution


def get_role_distribution(employees_ids, start_date, end_date, filters: ManagerFilterSchema,
                          limit: Optional[int] = None):
    """Get hour distribution by role"""

    tasks_filters = Q(
        timesheet__employee_id__in=employees_ids,
        created_at__gte=start_date,
        created_at__lte=end_date
    )

    if filters.project_id:
        tasks_filters &= Q(project_id=filters.project_id)
    if filters.activity_id:
        tasks_filters &= Q(activity_id=filters.activity_id)
    if filters.status:
        tasks_filters &= Q(timesheet__status=filters.status.value)

    # Get total hours for percentage calculation
    total_hours_qs = Task.objects.filter(tasks_filters)
    total_hours_result = total_hours_qs.aggregate(
        total=Sum('hour', output_field=DecimalField(max_digits=10, decimal_places=2))
    )
    total_department_hours = total_hours_result['total'] or Decimal('0.00')

    # Get role distribution
    role_stats = Task.objects.filter(tasks_filters).values(
        'timesheet__employee__position__id',
        'timesheet__employee__position__name'
    ).annotate(
        total_hours=Sum('hour'),
        active_employees=Count('timesheet__employee', distinct=True)
    ).order_by('-total_hours')

    # Apply limit if provided
    if limit:
        role_stats = role_stats[:limit]

    distribution = []
    for role in role_stats:
        if not role['timesheet__employee__position__id']:
            continue

        percentage = (float(role['total_hours']) / float(
            total_department_hours) * 100) if total_department_hours > 0 else 0
        avg_hours = float(role['total_hours']) / role['active_employees'] if role['active_employees'] > 0 else 0

        distribution.append(RoleDistributionSchema(
            role_id=role['timesheet__employee__position__id'],
            role_name=role['timesheet__employee__position__name'] or 'No Role',
            total_hours=str(role['total_hours']),
            active_employees=role['active_employees'],
            average_hours_per_role=avg_hours,
            percentage=percentage
        ))

    return distribution


def get_daily_evolution_detailed(employees_ids, start_date, end_date, filters: ManagerFilterSchema):
    """Get detailed daily hour evolution"""

    tasks_filters = Q(
        timesheet__employee_id__in=employees_ids,
        created_at__gte=start_date,
        created_at__lte=end_date
    )

    if filters.project_id:
        tasks_filters &= Q(project_id=filters.project_id)
    if filters.activity_id:
        tasks_filters &= Q(activity_id=filters.activity_id)
    if filters.status:
        tasks_filters &= Q(timesheet__status=filters.status.value)

    daily_stats = Task.objects.filter(tasks_filters).values('created_at').annotate(
        total_hours=Sum('hour'),
        active_employees=Count('timesheet__employee', distinct=True),
        active_projects=Count('project', distinct=True)
    ).order_by('created_at')

    evolution = []
    current_date = start_date

    # Create a dict for quick lookup
    stats_dict = {stat['created_at']: stat for stat in daily_stats}

    while current_date <= end_date:
        stat = stats_dict.get(current_date)

        if stat:
            avg_hours = float(stat['total_hours']) / stat['active_employees'] if stat['active_employees'] > 0 else 0
            is_weekend = current_date.weekday() >= 5

            evolution.append(DailyEvolutionSchema(
                date=current_date,
                total_hours=str(stat['total_hours']),
                active_employees=stat['active_employees'],
                active_projects=stat['active_projects'],
                average_hours_per_employee=avg_hours,
                day_of_week=current_date.strftime('%A'),
                is_weekend=is_weekend
            ))
        else:
            is_weekend = current_date.weekday() >= 5

            evolution.append(DailyEvolutionSchema(
                date=current_date,
                total_hours="0.00",
                active_employees=0,
                active_projects=0,
                average_hours_per_employee=0,
                day_of_week=current_date.strftime('%A'),
                is_weekend=is_weekend
            ))

        current_date += timedelta(days=1)

    return evolution


def get_weekly_summary(employees_ids, start_date, end_date, filters: ManagerFilterSchema):
    """Get weekly summary for optimization - SQLite compatible version"""

    tasks_filters = Q(
        timesheet__employee_id__in=employees_ids,
        created_at__gte=start_date,
        created_at__lte=end_date
    )

    if filters.project_id:
        tasks_filters &= Q(project_id=filters.project_id)
    if filters.activity_id:
        tasks_filters &= Q(activity_id=filters.activity_id)
    if filters.status:
        tasks_filters &= Q(timesheet__status=filters.status.value)

    # Get weekly aggregates - manual calculation for SQLite compatibility
    tasks_qs = Task.objects.filter(tasks_filters)

    # Group by week manually
    weekly_data = {}
    for task in tasks_qs.select_related('timesheet', 'project'):
        task_date = task.created_at
        week_start = task_date - timedelta(days=task_date.weekday())
        week_key = week_start.isoformat()

        if week_key not in weekly_data:
            weekly_data[week_key] = {
                'start_date': week_start,
                'end_date': week_start + timedelta(days=6),
                'total_hours': Decimal('0.00'),
                'active_employees': set(),
                'active_projects': set()
            }

        weekly_data[week_key]['total_hours'] += task.hour or Decimal('0.00')
        if task.timesheet and task.timesheet.employee_id:
            weekly_data[week_key]['active_employees'].add(task.timesheet.employee_id)
        if task.project_id:
            weekly_data[week_key]['active_projects'].add(task.project_id)

    evolution = []
    for week_data in weekly_data.values():
        avg_hours = float(week_data['total_hours']) / len(week_data['active_employees']) if week_data[
            'active_employees'] else 0

        evolution.append(DailyEvolutionSchema(
            date=week_data['start_date'],
            total_hours=str(week_data['total_hours']),
            active_employees=len(week_data['active_employees']),
            active_projects=len(week_data['active_projects']),
            average_hours_per_employee=avg_hours,
            day_of_week="Week Summary",
            is_weekend=False
        ))

    # Sort by date
    evolution.sort(key=lambda x: x.date)

    # If no data, return empty list with one entry for the period
    if not evolution:
        evolution.append(DailyEvolutionSchema(
            date=start_date,
            total_hours="0.00",
            active_employees=0,
            active_projects=0,
            average_hours_per_employee=0,
            day_of_week="No Data",
            is_weekend=False
        ))

    return evolution


def get_employee_kpis1(employee, start_date, end_date, filters: ManagerFilterSchema, department_employees_count: int):
    """Get KPIs for specific employee"""

    tasks_filters = Q(
        timesheet__employee=employee,
        created_at__gte=start_date,
        created_at__lte=end_date
    )

    if filters.project_id:
        tasks_filters &= Q(project_id=filters.project_id)
    if filters.activity_id:
        tasks_filters &= Q(activity_id=filters.activity_id)
    if filters.status:
        tasks_filters &= Q(timesheet__status=filters.status.value)

    tasks_qs = Task.objects.filter(tasks_filters)

    # Calculate hours
    total_hours_result = tasks_qs.aggregate(
        total=Sum('hour', output_field=DecimalField(max_digits=10, decimal_places=2))
    )
    total_hours = total_hours_result['total'] or Decimal('0.00')

    # Calculate days
    days_in_period = (end_date - start_date).days + 1
    worked_days = tasks_qs.dates('created_at', 'day').distinct().count()
    daily_average_hours = float(total_hours) / days_in_period if days_in_period > 0 else 0

    # Apply hour limit filters
    # These will be filtered later in get_top_employees function

    # Calculate submission rate
    ts_filters = Q(
        employee=employee,
        created_at__gte=start_date,
        created_at__lte=end_date
    )

    if filters.status:
        ts_filters &= Q(status=filters.status.value)

    timesheets_qs = Timesheet.objects.filter(ts_filters)
    total_timesheets = timesheets_qs.count()
    submitted_timesheets = timesheets_qs.filter(status=TimesheetStatusEnum.SUBMITTED.value).count()
    submission_rate = (submitted_timesheets / total_timesheets * 100) if total_timesheets > 0 else 0

    # Get projects worked count
    projects_worked = tasks_qs.exclude(project__isnull=True).values('project').distinct().count()

    # Get top project
    top_project = tasks_qs.exclude(project__isnull=True).values(
        'project__id', 'project__name'
    ).annotate(
        project_hours=Sum('hour')
    ).order_by('-project_hours').first()

    top_project_dict = None
    if top_project:
        top_project_dict = {
            'id': top_project['project__id'],
            'name': top_project['project__name'],
            'hours': str(top_project['project_hours'])
        }

    # Calculate overtime and weekend hours
    overtime_hours = Decimal('0.00')
    weekend_hours = tasks_qs.filter(
        created_at__week_day__in=[1, 7]  # Sunday=1, Saturday=7
    ).aggregate(total=Sum('hour'))['total'] or Decimal('0.00')

    # Create employee schema
    employee_schema = BasicEmployeeSchema(
        id=employee.id,
        full_name=employee.get_full_name(),
        role=employee.position.name if employee.position else None,
        role_id=employee.position.id if employee.position else None,
        active=employee.is_active,
        hire_date=employee.date_joined.date() if employee.date_joined else None,
        department_id=employee.department.id if employee.department else None,
        department_name=employee.department.name if employee.department else None
    )

    return EmployeeKPISchema(
        employee=employee_schema,
        total_hours=str(total_hours),
        worked_days=worked_days,
        daily_average_hours=daily_average_hours,
        submission_rate=submission_rate,
        approval_rate=None,
        projects_worked=projects_worked,
        top_project=top_project_dict,
        overtime_hours=str(overtime_hours),
        weekend_hours=str(weekend_hours),
        department_ranking=None,
        department_percentile=None
    )


def get_employee_kpis(employee, start_date, end_date, filters: ManagerFilterSchema, department_employees_count: int):
    """Get KPIs for specific employee"""

    tasks_filters = Q(
        timesheet__employee=employee,
        created_at__gte=start_date,
        created_at__lte=end_date
    )

    if filters.project_id:
        tasks_filters &= Q(project_id=filters.project_id)
    if filters.activity_id:
        tasks_filters &= Q(activity_id=filters.activity_id)
    if filters.status:
        tasks_filters &= Q(timesheet__status=filters.status.value)

    tasks_qs = Task.objects.filter(tasks_filters)

    # Calculate hours
    total_hours_result = tasks_qs.aggregate(
        total=Sum('hour', output_field=DecimalField(max_digits=10, decimal_places=2))
    )
    total_hours = total_hours_result['total'] or Decimal('0.00')

    # Calculate days
    days_in_period = (end_date - start_date).days + 1
    worked_days = tasks_qs.dates('created_at', 'day').distinct().count()

    # CORRIGIDO: Média diária baseada no TOTAL de dias no período
    daily_average_hours = float(total_hours) / days_in_period if days_in_period > 0 else 0

    # Calculate submission rate
    ts_filters = Q(
        employee=employee,
        created_at__gte=start_date,
        created_at__lte=end_date
    )

    if filters.status:
        ts_filters &= Q(status=filters.status.value)

    timesheets_qs = Timesheet.objects.filter(ts_filters)
    total_timesheets = timesheets_qs.count()
    submitted_timesheets = timesheets_qs.filter(status=TimesheetStatusEnum.SUBMITTED.value).count()
    submission_rate = (submitted_timesheets / total_timesheets * 100) if total_timesheets > 0 else 0

    # Get projects worked count
    projects_worked = tasks_qs.exclude(project__isnull=True).values('project').distinct().count()

    # Get top project
    top_project = tasks_qs.exclude(project__isnull=True).values(
        'project__id', 'project__name'
    ).annotate(
        project_hours=Sum('hour')
    ).order_by('-project_hours').first()

    top_project_dict = None
    if top_project:
        top_project_dict = {
            'id': top_project['project__id'],
            'name': top_project['project__name'],
            'hours': str(top_project['project_hours'])
        }

    # Calculate overtime and weekend hours
    daily_totals = tasks_qs.values('created_at').annotate(
        daily_sum=Sum('hour')
    )
    
    overtime_hours = sum(
        max(Decimal('0.00'), (row['daily_sum'] or Decimal('0.00')) - Decimal('8.00')) 
        for row in daily_totals
    )
    
    weekend_hours = tasks_qs.filter(
        created_at__week_day__in=[1, 7]  # Sunday=1, Saturday=7
    ).aggregate(total=Sum('hour'))['total'] or Decimal('0.00')

    # Create employee schema
    employee_schema = BasicEmployeeSchema(
        id=employee.id,
        full_name=employee.get_full_name(),
        role=employee.position.name if employee.position else None,
        role_id=employee.position.id if employee.position else None,
        active=employee.is_active,
        hire_date=employee.date_joined.date() if employee.date_joined else None,
        department_id=employee.department.id if employee.department else None,
        department_name=employee.department.name if employee.department else None
    )

    return EmployeeKPISchema(
        employee=employee_schema,
        total_hours=str(total_hours),
        worked_days=worked_days,
        daily_average_hours=daily_average_hours,  # AGORA: total_horas / total_dias_no_periodo
        submission_rate=submission_rate,
        approval_rate=None,
        projects_worked=projects_worked,
        top_project=top_project_dict,
        overtime_hours=str(overtime_hours),
        weekend_hours=str(weekend_hours),
        department_ranking=None,
        department_percentile=None
    )
def get_top_employees(employees, start_date, end_date, filters: ManagerFilterSchema, limit: int = 10):
    """Get top employees by hours with filters"""

    employee_kpis = []
    for employee in employees:
        kpi = get_employee_kpis(employee, start_date, end_date, filters, len(employees))

        # APPLY HOUR LIMIT FILTERS - NOVA FUNCIONALIDADE
        if filters.min_hour_limit and kpi.daily_average_hours < filters.min_hour_limit:
            continue
        if filters.max_hour_limit and kpi.daily_average_hours > filters.max_hour_limit:
            continue

        employee_kpis.append(kpi)

    # Sort by total hours
    employee_kpis.sort(key=lambda x: float(x.total_hours), reverse=True)

    return employee_kpis[:limit]


def generate_insights(kpis: DepartmentKPISchema, employees_count: int, start_date, end_date) -> List[str]:
    """Generate insights based on KPIs"""

    insights = []

    # Utilization insights
    if kpis.utilization_rate > 90:
        insights.append("🚀 Alta taxa de utilização: A equipa está a trabalhar na capacidade ideal")
    elif kpis.utilization_rate < 50:
        insights.append("📉 Baixa taxa de utilização: Considere alocar mais tarefas ou projetos")
    else:
        insights.append(f"📊 Utilização normal: {kpis.utilization_rate:.1f}% da capacidade")

    # Submission rate insights
    if kpis.submission_rate == 100:
        insights.append("✅ Todas as timesheets submetidas a tempo")
    elif kpis.submission_rate > 80:
        insights.append(f"📝 Boa taxa de submissão: {kpis.submission_rate:.1f}%")
    else:
        insights.append(f"⚠️ Baixa taxa de submissão: {kpis.submission_rate:.1f}% - Acompanhe com a equipa")

    # Productivity insights
    if kpis.daily_average_hours > 7:
        insights.append(f"⚡ Alta produtividade: {kpis.daily_average_hours:.1f}h de média diária")
    elif kpis.daily_average_hours < 4:
        insights.append(f"🐌 Baixa produtividade: {kpis.daily_average_hours:.1f}h de média diária")

    # Work pattern insights
    if kpis.days_without_records > (kpis.workdays * 0.3):  # 30% days without records
        insights.append(f"📅 {kpis.days_without_records} dias sem registos - verifique a disponibilidade da equipa")

    # Employee participation insights
    participation_rate = (kpis.employees_with_records / kpis.total_employees * 100) if kpis.total_employees > 0 else 0
    if participation_rate < 80:
        insights.append(f"👥 Baixa participação da equipa: {participation_rate:.1f}% da equipa tem registos")

    return insights[:5]


def generate_alerts(kpis: DepartmentKPISchema, filters: ManagerFilterSchema) -> List[SystemAlertSchema]:
    """Generate system alerts"""

    alerts = []
    now = timezone.now()

    # Low submission rate alert
    if kpis.submission_rate < 70:
        alerts.append(SystemAlertSchema(
            id=f"alert_submission_{now.timestamp()}",
            type="warning",
            title="Baixa Taxa de Submissão de Timesheets",
            description=f"Apenas {kpis.submission_rate:.1f}% das timesheets foram submetidas",
            priority=SeverityEnum.MEDIUM,
            creation_date=now,
            action_required=True,
            action_url="/manager/timesheets/pending",
            read=False
        ))

    # High utilization alert
    if kpis.utilization_rate > 95:
        alerts.append(SystemAlertSchema(
            id=f"alert_utilization_{now.timestamp()}",
            type="warning",
            title="Alta Utilização da Equipa",
            description=f"A equipa está com {kpis.utilization_rate:.1f}% de utilização - risco de sobrecarga",
            priority=SeverityEnum.MEDIUM,
            creation_date=now,
            action_required=True,
            read=False
        ))

    # No records alert
    if kpis.employees_with_records == 0:
        alerts.append(SystemAlertSchema(
            id=f"alert_norecords_{now.timestamp()}",
            type="critical",
            title="Sem Registos de Atividade",
            description="Nenhum membro da equipa registou horas neste período",
            priority=SeverityEnum.HIGH,
            creation_date=now,
            action_required=True,
            read=False
        ))

    return alerts


def get_cache_key(filters: ManagerFilterSchema, user_id: int, department_id: int) -> str:
    """Generate cache key from filters"""
    import hashlib
    import json

    # Create a hashable representation of filters
    filter_dict = filters.dict(exclude_none=True)
    filter_dict['user_id'] = user_id
    filter_dict['department_id'] = department_id
    filter_dict['timestamp'] = timezone.now().strftime("%Y%m%d%H")

    filter_str = json.dumps(filter_dict, sort_keys=True, default=str)
    filter_hash = hashlib.md5(filter_str.encode()).hexdigest()

    return f"{CACHE_KEY_PREFIX}{filter_hash}"


# ==================== MAIN ENDPOINTS ====================
@router.get("/manager/", response=ManagerDashboardResponseSchema)
def get_manager_dashboard(request, filters: ManagerFilterSchema = Query(...)):
    """
    Complete manager dashboard with comprehensive analytics
    Now properly handles show_details filter
    """

    try:
        # 1. Get manager's department
        department = get_manager_department(request)
        check_manager_access(request, department)

        # 2. Generate cache key
        cache_key = get_cache_key(filters, request.auth.id, department.id)

        # 3. Check cache if show_details is False (summary data can be cached longer)
        if not filters.show_details:
            cached_data = cache.get(cache_key)
            # COMENTADO PARA DEPURAÇÃO: Forçar cálculo live
            # if cached_data:
            #     return cached_data

        # 4. Get period dates
        date_range = get_period_date_range(
            period=filters.period.type,
            start_date=filters.period.start_date,
            end_date=filters.period.end_date
        )

        start_date = date_range['start_date']
        end_date = date_range['end_date']

        # Adjust future dates
        today = timezone.now().date()
        if end_date > today:
            end_date = today
        if start_date > today:
            start_date = today

        # 5. Get department employees
        employees = get_department_employees(
            department=department,
            include_manager=filters.include_manager,
            only_active=filters.only_active
        )

        # Apply employee filters
        if filters.employee_id:
            employees = employees.filter(id=filters.employee_id)
        elif filters.employee_ids:
            employees = employees.filter(id__in=filters.employee_ids)

        if filters.role_id:
            employees = employees.filter(position_id=filters.role_id)

        employee_ids = list(employees.values_list('id', flat=True))

        # 6. Calculate KPIs (always needed)
        kpis_dict = calculate_department_kpis(employee_ids, start_date, end_date, filters)
        kpis = DepartmentKPISchema(**kpis_dict)

        # 7. Get distributions with show_details optimization
        if filters.show_details:
            # FULL DETAILS MODE
            project_distribution = get_project_distribution(employee_ids, start_date, end_date, filters)
            role_distribution = get_role_distribution(employee_ids, start_date, end_date, filters)

            # Only get detailed daily evolution for periods <= 90 days
            days_in_period = (end_date - start_date).days + 1
            if days_in_period > 90:
                daily_evolution = get_weekly_summary(employee_ids, start_date, end_date, filters)
            else:
                daily_evolution = get_daily_evolution_detailed(employee_ids, start_date, end_date, filters)
        else:
            # SUMMARY MODE - Limited data for performance
            project_distribution = get_project_distribution(employee_ids, start_date, end_date, filters, limit=5)
            role_distribution = get_role_distribution(employee_ids, start_date, end_date, filters, limit=3)

            # Always use weekly summary for summary mode
            daily_evolution = get_weekly_summary(employee_ids, start_date, end_date, filters)

        # 8. Get top employees WITH hour limit filters
        top_employees = get_top_employees(employees, start_date, end_date, filters, limit=5)

        # 9. Get specific employee if requested
        specific_employee = None
        if filters.employee_id and filters.aggregation_level == AggregationLevelEnum.INDIVIDUAL:
            try:
                employee = employees.get(id=filters.employee_id)
                specific_employee = get_employee_kpis(employee, start_date, end_date, filters, len(employees))
            except User.DoesNotExist:
                pass

        # 10. Generate insights and alerts
        insights = generate_insights(kpis, len(employees), start_date, end_date)
        alerts = generate_alerts(kpis, filters)

        # 11. Build department schema
        department_schema = DepartmentSchema(
            id=department.id,
            name=department.name,
            acronym=getattr(department, 'acronym', None),
            manager_id=department.manager_id,
            manager_name=department.manager.get_full_name() if department.manager else None,
            active_employees=employees.filter(is_active=True).count(),
            total_employees=employees.count(),
            active_projects=len(project_distribution)
        )

        # 12. Build response with optimization based on show_details
        if filters.show_details:
            project_distribution_data = project_distribution[:20]  # Max 20 projects
            role_distribution_data = role_distribution
        else:
            # Limit data in summary mode
            project_distribution_data = project_distribution[:5]
            role_distribution_data = role_distribution[:3]
            daily_evolution = daily_evolution[:min(len(daily_evolution), 20)]  # Max 20 entries

        response_data = ManagerDashboardResponseSchema(
            metadata={
                "version": "2.0",
                "timestamp": timezone.now().isoformat(),
                "processing_time": None,
                "cache": {
                    "used": not filters.show_details,  # Cache only used for summary
                    "key": cache_key if not filters.show_details else None,
                    "expires_at": (timezone.now() + timedelta(seconds=CACHE_TIMEOUT)).isoformat()
                    if not filters.show_details else None
                }
            },
            context={
                "source": "manager_dashboard",
                "user_id": request.auth.id,
                "department_id": department.id,
                "filter_level": filters.aggregation_level.value,
                "data_mode": "detailed" if filters.show_details else "summary"
            },
            user={
                "id": request.auth.id,
                "username": request.auth.username,
                "email": request.auth.email,
                "is_manager": True
            },
            department=department_schema,
            filters=filters.dict(),
            analysis_period={
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "days": (end_date - start_date).days + 1,
                "label": date_range['label']
            },
            data={
                "summary": kpis,
                "project_distribution": project_distribution_data,
                "role_distribution": role_distribution_data,
                "daily_evolution": daily_evolution,
                "top_employees": top_employees,
                "specific_employee": specific_employee,
                "complete_ranking": None,
                "recent_activities": {
                    "timesheets": [],
                    "tasks": [],
                    "approvals": [],
                    "comments": []
                }
            },
            analysis={
                "active_alerts": alerts,
                "risk_indicators": [],
                "insights": insights,
                "highlights": [
                    f"Total hours: {float(kpis.total_hours):.1f}h",
                    f"Team size: {kpis.total_employees} employees",
                    f"Active projects: {kpis.active_projects}"
                ],
                "attention_points": [
                    f"Submission rate: {kpis.submission_rate:.1f}%",
                    f"Utilization: {kpis.utilization_rate:.1f}%"
                ] if kpis.submission_rate < 80 else []
            },
            recommendations={
                "priority_actions": [],
                "improvement_suggestions": [
                    "Review pending timesheets",
                    "Check team workload balance",
                    "Monitor project deadlines"
                ],
                "metrics_to_monitor": [
                    {"metric": "utilization_rate", "target": 75},
                    {"metric": "submission_rate", "target": 100},
                    {"metric": "daily_average_hours", "target": 7.5}
                ]
            },
            resources={
                "urls": {
                    "export": f"/api/manager/dashboard/export/?start_date={start_date}&end_date={end_date}",
                    "detailed_report": f"/api/manager/reports/detailed/?start_date={start_date}&end_date={end_date}",
                    "timesheet_management": "/manager/timesheets/",
                    "team_dashboard": f"/dashboard/team?department={department.id}"
                },
                "visualization_options": [
                    {"type": "bar", "title": "Project Distribution"},
                    {"type": "line", "title": "Daily Evolution"},
                    {"type": "pie", "title": "Role Distribution"}
                ],
                "system_limits": {
                    "max_results": 1000,
                    "max_period_days": 365,
                    "cache_minutes": 5
                }
            },
            data_quality={
                "completeness": 95.0,
                "freshness": timezone.now().isoformat(),
                "sources": ["timesheets", "tasks", "employees"],
                "notes": ["Data processed in real-time"]
            }
        )

        # 13. Cache the response if in summary mode
        if not filters.show_details:
            cache.set(cache_key, response_data, CACHE_TIMEOUT)

        return response_data

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error in manager dashboard: {str(e)}", exc_info=True)

        # Create minimal valid response with error
        return ManagerDashboardResponseSchema(
            metadata={
                "version": "2.0",
                "timestamp": timezone.now().isoformat(),
                "error": str(e)
            },
            context={
                "source": "manager_dashboard",
                "user_id": request.auth.id if request.auth else None,
                "error": True
            },
            user={
                "id": request.auth.id if request.auth else None,
                "username": request.auth.username if request.auth else None,
                "is_manager": True
            },
            department=DepartmentSchema(
                id=0,
                name="Error",
                active_employees=0,
                total_employees=0,
                active_projects=0
            ),
            filters=filters.dict() if 'filters' in locals() else {},
            analysis_period={
                "start_date": timezone.now().date().isoformat(),
                "end_date": timezone.now().date().isoformat(),
                "days": 1,
                "label": "Error Period"
            },
            data={
                "summary": DepartmentKPISchema(
                    total_hours="0.00",
                    daily_average_hours=0,
                    average_hours_per_employee=0,
                    utilization_rate=0,
                    submission_rate=0,
                    approval_rate=None,
                    total_employees=0,
                    employees_with_records=0,
                    total_projects=0,
                    active_projects=0,
                    worked_days=0,
                    workdays=0,
                    days_without_records=0,
                    efficiency_score=0,
                    participation_rate=0,
                    productivity_score=0
                ),
                "project_distribution": [],
                "role_distribution": [],
                "daily_evolution": [],
                "top_employees": [],
                "specific_employee": None,
                "complete_ranking": None,
                "recent_activities": {
                    "timesheets": [],
                    "tasks": [],
                    "approvals": [],
                    "comments": []
                }
            },
            analysis={
                "active_alerts": [],
                "risk_indicators": [],
                "insights": [f"Error loading dashboard: {str(e)[:100]}"],
                "highlights": [],
                "attention_points": []
            },
            recommendations={
                "priority_actions": [],
                "improvement_suggestions": ["Check system logs for details"],
                "metrics_to_monitor": []
            },
            resources={
                "urls": {
                    "export": "#",
                    "detailed_report": "#",
                    "timesheet_management": "#",
                    "team_dashboard": "#"
                },
                "visualization_options": [],
                "system_limits": {
                    "max_results": 1000,
                    "max_period_days": 365,
                    "cache_minutes": 5
                }
            },
            data_quality={
                "completeness": 0.0,
                "freshness": timezone.now().isoformat(),
                "sources": [],
                "notes": ["Error occurred"]
            }
        )

@router.get("/manager/filter-options/", response=ManagerFilterOptionsSchema)
def get_manager_filter_options(request):
    """Get available filter options for manager dashboard"""

    try:
        department = get_manager_department(request)
        check_manager_access(request, department)

        # Get employees
        employees = get_department_employees(department, only_active=True)
        employees_list = []

        for emp in employees:
            employees_list.append(BasicEmployeeSchema(
                id=emp.id,
                full_name=emp.get_full_name(),
                role=emp.position.name if emp.position else None,
                role_id=emp.position.id if emp.position else None,
                active=emp.is_active,
                hire_date=emp.date_joined.date() if emp.date_joined else None,
                department_id=department.id,
                department_name=department.name
            ))

        # Get projects used by department
        project_objs = Task.objects.filter(
            timesheet__employee__in=employees
        ).exclude(
            Q(project__isnull=True) | Q(project__name__isnull=True)
        ).values(
            'project_id', 'project__name'
        ).distinct().order_by('project__name')

        projects_list = []
        for proj in project_objs:
            # Get actual hours for this project
            actual_hours = Task.objects.filter(
                project_id=proj['project_id'],
                timesheet__employee__in=employees
            ).aggregate(
                total=Sum('hour', output_field=DecimalField(max_digits=10, decimal_places=2))
            )['total'] or Decimal('0.00')

            projects_list.append(ProjectSchema(
                id=proj['project_id'],
                name=proj['project__name'],
                actual_hours=str(actual_hours)
            ))

        # Get activities
        activities = Activity.objects.filter(
            department=department,
            is_active=True
        ).values('id', 'name').order_by('name')

        activities_list = []
        for act in activities:
            activities_list.append({
                "id": act['id'],
                "name": act['name'],
                "billable": True
            })

        # Get roles from user positions
        from django.db.models import Count
        roles_list = []
        role_data = employees.exclude(position__isnull=True).values(
            'position__id', 'position__name'
        ).annotate(
            employee_count=Count('id')
        ).distinct().order_by('position__name')

        for role in role_data:
            roles_list.append({
                "id": role['position__id'],
                "name": role['position__name'],
                "employee_count": role['employee_count'],
                "description": f"{role['employee_count']} employees"
            })

        return ManagerFilterOptionsSchema(
            projects=projects_list,
            activities=activities_list,
            employees=employees_list,
            roles=roles_list
        )

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error getting filter options: {str(e)}", exc_info=True)

        return ManagerFilterOptionsSchema(
            projects=[],
            activities=[],
            employees=[],
            roles=[]
        )


@router.get("/manager/quick-stats/", response=Dict[str, Any])
def get_quick_stats(request):
    """Get quick statistics for dashboard (optimized for speed)"""

    try:
        department = get_manager_department(request)
        check_manager_access(request, department)

        # Current month
        today = timezone.now().date()
        start_of_month = today.replace(day=1)

        # Get employees
        employees = get_department_employees(department, only_active=True)
        employee_ids = list(employees.values_list('id', flat=True))

        # Get tasks for current month
        tasks_qs = Task.objects.filter(
            timesheet__employee_id__in=employee_ids,
            created_at__gte=start_of_month,
            created_at__lte=today
        )

        # Calculate totals
        total_hours_result = tasks_qs.aggregate(
            total=Sum('hour', output_field=DecimalField(max_digits=10, decimal_places=2))
        )
        total_hours = total_hours_result['total'] or Decimal('0.00')

        # Today's hours
        todays_tasks = tasks_qs.filter(created_at=today)
        todays_hours_result = todays_tasks.aggregate(
            total=Sum('hour', output_field=DecimalField(max_digits=10, decimal_places=2))
        )
        todays_hours = todays_hours_result['total'] or Decimal('0.00')

        # Pending timesheets
        pending_timesheets = Timesheet.objects.filter(
            employee_id__in=employee_ids,
            status=TimesheetStatusEnum.DRAFT.value,
            created_at__gte=start_of_month
        ).count()

        # Active projects
        active_projects = tasks_qs.exclude(project__isnull=True).values('project').distinct().count()

        # Calculate utilization
        expected_hours = len(employee_ids) * today.day * 8  # 8 hours per day
        utilization_rate = (float(total_hours) / expected_hours * 100) if expected_hours > 0 else 0

        return {
            "department": {
                "id": department.id,
                "name": department.name,
                "employee_count": len(employee_ids)
            },
            "stats": {
                "monthly_hours": float(total_hours),
                "daily_average": float(total_hours) / today.day if today.day > 0 else 0,
                "pending_approvals": pending_timesheets,
                "active_projects": active_projects,
                "todays_hours": float(todays_hours),
                "utilization_rate": utilization_rate
            },
            "timestamp": timezone.now().isoformat(),
            "period": {
                "start": start_of_month.isoformat(),
                "end": today.isoformat()
            }
        }

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error getting quick stats: {str(e)}", exc_info=True)

        return {
            "error": "stats_error",
            "code": "STATS_ERROR",
            "message": f"Error loading statistics: {str(e)}",
            "timestamp": timezone.now()
        }


@router.get("/manager/summary/", response=Dict[str, Any])
def get_dashboard_summary(
        request,
        period: PeriodEnum = Query(PeriodEnum.MONTH),
        start_date: Optional[date] = Query(None),
        end_date: Optional[date] = Query(None),
        include_manager: bool = False
):
    """
    Ultra-optimized dashboard summary endpoint
    Returns only essential data for quick loading
    """
    try:
        department = get_manager_department(request)
        check_manager_access(request, department)

        # Get period
        date_range = get_period_date_range(period, start_date, end_date)
        start_date = date_range['start_date']
        end_date = date_range['end_date']

        # Adjust dates
        today = timezone.now().date()
        if end_date > today:
            end_date = today

        # Get employees
        employees = get_department_employees(
            department=department,
            include_manager=include_manager,
            only_active=True
        )
        employee_ids = list(employees.values_list('id', flat=True))

        # Simple KPIs calculation
        tasks_qs = Task.objects.filter(
            timesheet__employee_id__in=employee_ids,
            created_at__gte=start_date,
            created_at__lte=end_date
        )

        # Basic aggregates
        stats = tasks_qs.aggregate(
            total_hours=Sum('hour'),
            employee_count=Count('timesheet__employee', distinct=True),
            project_count=Count('project', distinct=True),
            day_count=Count('created_at', distinct=True)
        )

        total_hours = stats['total_hours'] or Decimal('0.00')
        employee_count = stats['employee_count'] or 0
        project_count = stats['project_count'] or 0
        day_count = stats['day_count'] or 0

        # Calculate daily average
        days_in_period = (end_date - start_date).days + 1
        daily_average = float(total_hours) / day_count if day_count > 0 else 0

        # Top 3 projects
        top_projects = tasks_qs.exclude(project__isnull=True).values(
            'project_id', 'project__name'
        ).annotate(
            hours=Sum('hour'),
            employee_count=Count('timesheet__employee', distinct=True)
        ).order_by('-hours')[:3]

        # Top 3 employees
        top_employees = tasks_qs.values(
            'timesheet__employee_id',
            'timesheet__employee__first_name',
            'timesheet__employee__last_name'
        ).annotate(
            hours=Sum('hour')
        ).order_by('-hours')[:3]

        return {
            "department": {
                "id": department.id,
                "name": department.name,
                "total_employees": employees.count()
            },
            "period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
                "days": days_in_period
            },
            "stats": {
                "total_hours": float(total_hours),
                "daily_average": daily_average,
                "active_employees": employee_count,
                "active_projects": project_count,
                "days_with_data": day_count
            },
            "top_projects": [
                {
                    "id": p['project_id'],
                    "name": p['project__name'],
                    "hours": float(p['hours'] or 0),
                    "employee_count": p['employee_count']
                }
                for p in top_projects
            ],
            "top_employees": [
                {
                    "id": e['timesheet__employee_id'],
                    "name": f"{e['timesheet__employee__first_name']} {e['timesheet__employee__last_name']}",
                    "hours": float(e['hours'] or 0)
                }
                for e in top_employees
            ],
            "timestamp": timezone.now().isoformat(),
            "data_mode": "ultra_summary"
        }

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error in dashboard summary: {str(e)}", exc_info=True)

        return {
            "error": str(e),
            "timestamp": timezone.now().isoformat()
        }