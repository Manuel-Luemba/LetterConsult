# core/dashboard/api_coordenador.py
from django.core.exceptions import PermissionDenied
from ninja import Router, Query
from django.db.models import Q, Sum, Count
from django.db.models import DecimalField
from datetime import timedelta, timezone

import statistics

from rest_framework.decorators import permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication

from .schemas_manager import *
from .schemas_colaborador import PeriodEnum as ColaboradorPeriodEnum
from .base.periods import get_period_date_range
from core.timesheet.models import Task, Timesheet
from core.user.models import User
from .schemas_manager2 import SeverityEnum
from ..activity.models import Activity

router = Router(tags=["Manager Dashboard"])


# ==================== HELPER FUNCTIONS ====================
def get_manager_department(request):
    """Get authenticated manager's department"""
    user = request.auth or request.user
    if not user or not user.is_authenticated:
        raise PermissionDenied("User not authenticated")

    if not user.department:
        raise PermissionDenied("Manager without assigned department")

    return user.department


def get_department_employees(department):
    """Get all employees in the department"""
    return User.objects.filter(department=department, is_active=True)


def calculate_department_kpis(employee_ids, start_date, end_date, project_id=None, activity_id=None, status=None):
    """Calculate aggregated department KPIs applying filters"""

    # Department tasks in the period
    tasks_filters = Q(
        timesheet__employee__id__in=employee_ids,
        created_at__gte=start_date,
        created_at__lte=end_date
    )

    if project_id:
        tasks_filters &= Q(project_id=project_id)
    if activity_id:
        tasks_filters &= Q(activity_id=activity_id)
    if status:
        tasks_filters &= Q(timesheet__status=status)

    tasks_qs = Task.objects.filter(tasks_filters)

    # Department timesheets
    ts_filters = Q(
        employee__id__in=employee_ids,
        created_at__gte=start_date,
        created_at__lte=end_date
    )
    if status:
        ts_filters &= Q(status=status)

    timesheets_qs = Timesheet.objects.filter(ts_filters)

    # 1. GENERAL PRODUCTIVITY
    total_hours_result = tasks_qs.aggregate(
        total=Sum('hour', output_field=DecimalField(max_digits=10, decimal_places=2))
    )
    total_hours = total_hours_result['total'] or Decimal('0.00')

    active_employees = set(tasks_qs.values_list('timesheet__employee_id', flat=True).distinct())
    active_employee_count = len(active_employees)

    avg_hours_per_employee = (
        float(total_hours) / active_employee_count
        if active_employee_count > 0 else 0
    )

    # 2. PROJECT DISTRIBUTION
    project_stats = tasks_qs.exclude(project__isnull=True).values(
        'project__id', 'project__name', 'project__code'
    ).annotate(
        total_hours=Sum('hour'),
        employee_count=Count('timesheet__employee', distinct=True),
        task_count=Count('id')
    ).order_by('-total_hours')

    hours_by_project = []
    top_project = None
    top_project_percentage = None
    project_concentration = 0.0

    if project_stats:
        # Top project
        top = project_stats[0]
        top_project = top['project__name']
        if total_hours > 0:
            top_project_percentage = (float(top['total_hours']) / float(total_hours)) * 100

        # Concentration in top 3 projects
        top_3_hours = sum(float(p['total_hours']) for p in project_stats[:3])
        if total_hours > 0:
            project_concentration = (top_3_hours / float(total_hours)) * 100

        # Format for response
        for proj in project_stats[:10]:  # Limit to 10 projects
            hours_by_project.append({
                'id': proj['project__id'],
                'name': proj['project__name'],
                'code': proj['project__code'],
                'total_hours': proj['total_hours'],
                'employee_count': proj['employee_count'],
                'task_count': proj['task_count'],
                'percentage': (float(proj['total_hours']) / float(total_hours)) * 100 if total_hours > 0 else 0
            })

    # 3. BEHAVIORS
    # Weekend hours
    weekend_tasks = tasks_qs.filter(
        Q(created_at__week_day=7) | Q(created_at__week_day=1)  # Sunday=1, Saturday=7
    )
    weekend_hours_result = weekend_tasks.aggregate(
        total=Sum('hour', output_field=DecimalField(max_digits=10, decimal_places=2))
    )
    weekend_hours = weekend_hours_result['total'] or Decimal('0.00')
    weekend_hours_percentage = (
        (float(weekend_hours) / float(total_hours)) * 100
        if total_hours > 0 else 0
    )

    # Overload days (>8h per employee per day)
    daily_overload = tasks_qs.values(
        'created_at', 'timesheet__employee'
    ).annotate(
        daily_hours=Sum('hour')
    ).filter(daily_hours__gt=8).count()

    # 4. RECORD QUALITY
    submitted_timesheets = timesheets_qs.filter(status='submetido').count()
    total_timesheets = timesheets_qs.count()
    submission_rate = (
        (submitted_timesheets / total_timesheets * 100)
        if total_timesheets > 0 else 0
    )

    # Pending timesheets
    pending_timesheets = timesheets_qs.filter(status='rascunho')
    pending_count = pending_timesheets.count()

    oldest_pending_days = None
    if pending_count > 0:
        oldest = pending_timesheets.order_by('created_at').first()
        if oldest and oldest.created_at:
            oldest_pending_days = (timezone.now().date() - oldest.created_at).days

    # 5. WORKLOAD BALANCE
    # Hours per employee
    employee_hours = tasks_qs.values(
        'timesheet__employee_id', 'timesheet__employee__first_name', 'timesheet__employee__last_name'
    ).annotate(
        total=Sum('hour')
    ).order_by('-total')

    load_balance_index = 100.0  # Ideal
    top_employee_hours = None
    bottom_employee_hours = None
    hours_std_dev = None

    if employee_hours.count() > 1:
        hours_list = [float(ch['total'] or 0) for ch in employee_hours]
        if hours_list:
            # Balance index (0-100, where 100 is perfect balance)
            avg_hours = sum(hours_list) / len(hours_list)
            if avg_hours > 0:
                cv = (statistics.stdev(hours_list) / avg_hours) * 100
                load_balance_index = max(0, 100 - min(cv, 100))

            top_employee_hours = employee_hours.first()['total']
            bottom_employee_hours = employee_hours.last()['total']
            hours_std_dev = statistics.stdev(hours_list) if len(hours_list) > 1 else 0

    # 6. TRENDS (simplified)
    # Productivity peak
    peak_day_data = tasks_qs.values('created_at').annotate(
        day_hours=Sum('hour')
    ).order_by('-day_hours').first()

    peak_day = None
    peak_day_hours = None
    if peak_day_data:
        peak_day = peak_day_data['created_at'].strftime('%A') if peak_day_data['created_at'] else None
        peak_day_hours = peak_day_data['day_hours']

    # Calculate department productivity index
    days_in_period = (end_date - start_date).days + 1
    expected_hours = active_employee_count * days_in_period * 8  # 8h/day ideal
    department_productivity_index = (
        (float(total_hours) / expected_hours * 100)
        if expected_hours > 0 else 0
    )

    # 7. ADDITIONAL METRICS
    # Utilization rate (simplified calculation)
    total_work_days = days_in_period * active_employee_count if active_employee_count > 0 else 1
    theoretical_hours = total_work_days * 8
    utilization_rate = (float(total_hours) / theoretical_hours * 100) if theoretical_hours > 0 else 0

    # Efficiency score (combination of submission rate and balance)
    efficiency_score = (submission_rate * 0.6) + (load_balance_index * 0.4)

    return {
        'total_hours': total_hours,
        'avg_hours_per_employee': round(avg_hours_per_employee, 2),
        'active_employee_count': active_employee_count,
        'department_productivity_index': round(min(department_productivity_index, 150), 1),

        'hours_by_project': hours_by_project,
        'top_project': top_project,
        'top_project_percentage': round(top_project_percentage, 1) if top_project_percentage else None,
        'project_concentration': round(project_concentration, 1),

        'weekend_hours': weekend_hours,
        'weekend_hours_percentage': round(weekend_hours_percentage, 1),
        'overload_days': daily_overload,

        'submission_rate': round(submission_rate, 1),
        'pending_timesheets_count': pending_count,
        'pending_timesheets_oldest_days': oldest_pending_days,

        'load_balance_index': round(load_balance_index, 1),
        'top_employee_hours': top_employee_hours,
        'bottom_employee_hours': bottom_employee_hours,
        'hours_std_dev': round(hours_std_dev, 2) if hours_std_dev else None,

        'peak_day': peak_day,
        'peak_day_hours': peak_day_hours,

        'utilization_rate': round(min(utilization_rate, 100), 1),
        'efficiency_score': round(min(efficiency_score, 100), 1),
        'total_employees': len(employee_ids),
        'workdays': days_in_period,
        'worked_days': active_employee_count * days_in_period if active_employee_count > 0 else 0
    }


def generate_department_insights(kpis_data: Dict[str, Any], employees_count: int) -> List[str]:
    """Generate automatic insights for the department"""
    insights = []

    # 1. Productivity
    prod_index = kpis_data.get('department_productivity_index', 0)
    if prod_index > 120:
        insights.append(f"🚀 Excellent productivity! {prod_index:.0f}% above expected")
    elif prod_index < 80:
        insights.append(f"📉 Below average productivity: {prod_index:.0f}% of expected")
    else:
        insights.append(f"📊 Productivity within expected range: {prod_index:.0f}%")

    # 2. Workload balance
    balance = kpis_data.get('load_balance_index', 100)
    if balance < 70:
        insights.append("⚖️  Attention to workload balance between employees")
    elif balance > 90:
        insights.append("✅ Excellent work distribution in the team")

    # 3. Projects
    concentration = kpis_data.get('project_concentration', 0)
    if concentration > 80:
        insights.append(f"🎯 Intense focus on few projects ({concentration:.0f}% in top 3)")

    # 4. Weekends
    weekend_pct = kpis_data.get('weekend_hours_percentage', 0)
    if weekend_pct > 15:
        insights.append(f"🏠 {weekend_pct:.0f}% of work on weekends")

    # 5. Submissions
    sub_rate = kpis_data.get('submission_rate', 0)
    pending = kpis_data.get('pending_timesheets_count', 0)
    if sub_rate < 80:
        insights.append(f"📝 Low submission rate: {sub_rate:.0f}% ({pending} pending)")
    elif sub_rate == 100:
        insights.append("✅ All timesheets have been submitted!")

    # 6. Overload
    overload = kpis_data.get('overload_days', 0)
    if overload > 0:
        insights.append(f"⚠️  {overload} days with workload over 8h")

    # 7. Utilization
    utilization = kpis_data.get('utilization_rate', 0)
    if utilization > 90:
        insights.append(f"🔥 High utilization rate: {utilization:.0f}%")
    elif utilization < 60:
        insights.append(f"📉 Low utilization rate: {utilization:.0f}%")

    return insights[:7]


def generate_department_alerts(kpis_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Generate critical alerts for the manager"""
    alerts = []

    # 1. Very old pending timesheets
    oldest_pending = kpis_data.get('pending_timesheets_oldest_days')
    if oldest_pending and oldest_pending > 7:
        alerts.append({
            "id": "old_pending_timesheet",
            "type": "warning",
            "title": "Old Pending Timesheet",
            "description": f"Timesheet pending for {oldest_pending} days",
            "priority": SeverityEnum.HIGH,
            "creation_date": timezone.now(),
            "action_required": True,
            "action_url": "/timesheets/pending/"
        })

    # 2. Very low productivity
    prod_index = kpis_data.get('department_productivity_index', 100)
    if prod_index < 50:
        alerts.append({
            "id": "critical_productivity",
            "type": "critical",
            "title": "Critical Productivity",
            "description": f"Critical productivity: {prod_index:.0f}% of expected",
            "priority": SeverityEnum.HIGH,
            "creation_date": timezone.now(),
            "action_required": True
        })

    # 3. High concentration in one project
    concentration = kpis_data.get('project_concentration', 0)
    if concentration > 90:
        alerts.append({
            "id": "high_project_concentration",
            "type": "warning",
            "title": "High Project Concentration",
            "description": "90%+ of work in only 3 projects",
            "priority": SeverityEnum.MEDIUM,
            "creation_date": timezone.now(),
            "action_required": False
        })

    # 4. Many weekend hours
    weekend_pct = kpis_data.get('weekend_hours_percentage', 0)
    if weekend_pct > 30:
        alerts.append({
            "id": "high_weekend_hours",
            "type": "warning",
            "title": "High Weekend Hours",
            "description": f"{weekend_pct:.0f}% of work on weekends",
            "priority": SeverityEnum.MEDIUM,
            "creation_date": timezone.now(),
            "action_required": False
        })

    return alerts


def generate_risk_indicators(kpis_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Generate risk indicators for the department"""
    risks = []

    # 1. Workload imbalance
    balance = kpis_data.get('load_balance_index', 100)
    if balance < 60:
        risks.append({
            "type": "overload",
            "severity": SeverityEnum.HIGH,
            "title": "Workload Imbalance",
            "description": "Significant imbalance in workload distribution",
            "affected_employees": ["Multiple"],
            "affected_count": kpis_data.get('active_employee_count', 0),
            "suggested_action": "Review and redistribute tasks",
            "detection_date": timezone.now()
        })

    # 2. Low submission rate
    sub_rate = kpis_data.get('submission_rate', 0)
    if sub_rate < 70:
        risks.append({
            "type": "submission_delay",
            "severity": SeverityEnum.MEDIUM,
            "title": "Low Submission Rate",
            "description": f"Only {sub_rate:.0f}% of timesheets submitted",
            "affected_employees": ["Department"],
            "affected_count": kpis_data.get('total_employees', 0),
            "suggested_action": "Follow up with team about timesheet submission",
            "detection_date": timezone.now()
        })

    # 3. Many overload days
    overload = kpis_data.get('overload_days', 0)
    if overload > 5:
        risks.append({
            "type": "overload",
            "severity": SeverityEnum.MEDIUM,
            "title": "Frequent Overload",
            "description": f"{overload} days with overload (>8h)",
            "affected_employees": ["Multiple"],
            "affected_count": kpis_data.get('active_employee_count', 0),
            "suggested_action": "Monitor workload and consider task redistribution",
            "detection_date": timezone.now()
        })

    return risks


def get_employee_summary(employee, start_date, end_date, project_id=None, activity_id=None, status=None):
    """Calculate individual employee summary applying filters"""

    tasks_filters = Q(
        timesheet__employee=employee,
        created_at__gte=start_date,
        created_at__lte=end_date
    )
    if project_id:
        tasks_filters &= Q(project_id=project_id)
    if activity_id:
        tasks_filters &= Q(activity_id=activity_id)
    if status:
        tasks_filters &= Q(timesheet__status=status)

    tasks_qs = Task.objects.filter(tasks_filters)

    ts_filters = Q(
        employee=employee,
        created_at__gte=start_date,
        created_at__lte=end_date
    )
    if status:
        ts_filters &= Q(status=status)

    timesheets_qs = Timesheet.objects.filter(ts_filters)

    # Basic calculations
    total_hours_result = tasks_qs.aggregate(
        total=Sum('hour', output_field=DecimalField(max_digits=10, decimal_places=2))
    )
    total_hours = total_hours_result['total'] or Decimal('0.00')

    days_with_tasks = tasks_qs.dates('created_at', 'day').distinct().count()
    days_in_period = (end_date - start_date).days + 1
    work_frequency = (days_with_tasks / days_in_period * 100) if days_in_period > 0 else 0
    avg_daily_hours = float(total_hours) / days_in_period if days_in_period > 0 else 0

    # Timesheets
    submitted_timesheets = timesheets_qs.filter(status='submetido').count()
    pending_timesheets = timesheets_qs.filter(status='rascunho').count()
    submission_rate = (
        (submitted_timesheets / timesheets_qs.count() * 100)
        if timesheets_qs.count() > 0 else 0
    )

    # Projects worked on
    projects_worked = tasks_qs.exclude(project__isnull=True).values('project').distinct().count()

    # Weekend hours
    weekend_tasks = tasks_qs.filter(
        Q(created_at__week_day=7) | Q(created_at__week_day=1)
    )
    weekend_hours_result = weekend_tasks.aggregate(
        total=Sum('hour', output_field=DecimalField(max_digits=10, decimal_places=2))
    )
    weekend_hours = weekend_hours_result['total'] or Decimal('0.00')

    # Last activity
    last_task = tasks_qs.order_by('-created_at').first()
    last_activity = last_task.created_at if last_task else None

    return {
        'id': employee.id,
        'full_name': employee.get_full_name(),
        'position': employee.position.name if employee.position else None,
        'total_hours': total_hours,
        'avg_daily_hours': round(avg_daily_hours, 2),
        'work_frequency': round(work_frequency, 1),
        'days_with_tasks': days_with_tasks,
        'submitted_timesheets': submitted_timesheets,
        'pending_timesheets': pending_timesheets,
        'submission_rate': round(submission_rate, 1),
        'projects_worked': projects_worked,
        'weekend_hours': weekend_hours,
        'last_activity': last_activity
    }


def get_daily_evolution(employee_ids, start_date, end_date, project_id=None, activity_id=None, status=None):
    """Get daily hour evolution applying filters"""
    # Group by day
    tasks_filters = Q(
        timesheet__employee__id__in=employee_ids,
        created_at__gte=start_date,
        created_at__lte=end_date
    )
    if project_id:
        tasks_filters &= Q(project_id=project_id)
    if activity_id:
        tasks_filters &= Q(activity_id=activity_id)
    if status:
        tasks_filters &= Q(timesheet__status=status)

    daily_stats = Task.objects.filter(tasks_filters).values('created_at').annotate(
        total_hours=Sum('hour'),
        employee_count=Count('timesheet__employee', distinct=True)
    ).order_by('created_at')

    result = []

    # Fill all days in period
    current_date = start_date
    while current_date <= end_date:
        day_stats = next(
            (d for d in daily_stats if d['created_at'] == current_date),
            None
        )

        if day_stats:
            avg_hours = (
                float(day_stats['total_hours']) / day_stats['employee_count']
                if day_stats['employee_count'] > 0 else 0
            )

            # Get unique projects for the day
            day_projects = Task.objects.filter(
                created_at=current_date,
                timesheet__employee__id__in=employee_ids
            ).values('project').distinct().count()

            result.append({
                'date': current_date,
                'total_hours': day_stats['total_hours'],
                'employee_count': day_stats['employee_count'],
                'project_count': day_projects,
                'avg_hours': round(avg_hours, 2),
                'day_of_week': current_date.strftime('%A'),
                'is_weekend': current_date.weekday() >= 5
            })
        else:
            result.append({
                'date': current_date,
                'total_hours': Decimal('0.00'),
                'employee_count': 0,
                'project_count': 0,
                'avg_hours': 0.0,
                'day_of_week': current_date.strftime('%A'),
                'is_weekend': current_date.weekday() >= 5
            })

        current_date += timedelta(days=1)

    return result


def convert_colaborador_period_to_manager_period(period: ColaboradorPeriodEnum) -> PeriodEnum:
    """Convert PeriodEnum from collaborator schema to manager schema"""
    mapping = {
        "today": "today",
        "yesterday": "yesterday",
        "week": "week",
        "last_week": "last_week",
        "month": "month",
        "last_month": "last_month",
        "quarter": "quarter",
        "year": "year",
        "custom": "custom"
    }

    period_str = period.value if hasattr(period, 'value') else str(period)
    return PeriodEnum(mapping.get(period_str, "month"))


def create_manager_filter_from_params(
        period: ColaboradorPeriodEnum,
        start_date: Optional[date],
        end_date: Optional[date],
        project_id: Optional[int],
        activity_id: Optional[int],
        status: Optional[str],
        employee_ids: List[int],
        employee_id: Optional[int],
        role_id: Optional[int],
        include_manager: bool,
        aggregation_level: str,
        only_active: bool,
        show_details: bool,
        min_hour_limit: Optional[float],
        max_hour_limit: Optional[float]
) -> ManagerFilterSchema:
    """Create ManagerFilterSchema from query parameters"""

    # Convert period
    period_type = convert_colaborador_period_to_manager_period(period)

    # Convert status
    status_enum = None
    if status:
        status_mapping = {
            "rascunho": TimesheetStatusEnum.DRAFT,
            "submetido": TimesheetStatusEnum.SUBMITTED,
            "draft": TimesheetStatusEnum.DRAFT,
            "submitted": TimesheetStatusEnum.SUBMITTED
        }
        status_enum = status_mapping.get(status)

    # Create period schema
    period_schema = PeriodSchema(
        type=period_type,
        start_date=start_date,
        end_date=end_date
    )

    # Convert aggregation level
    aggregation_level_enum = AggregationLevelEnum(
        aggregation_level) if aggregation_level else AggregationLevelEnum.DEPARTMENT

    # If employee_id is provided, add it to employee_ids
    final_employee_ids = employee_ids.copy() if employee_ids else []
    if employee_id and employee_id not in final_employee_ids:
        final_employee_ids.append(employee_id)

    return ManagerFilterSchema(
        period=period_schema,
        project_id=project_id,
        activity_id=activity_id,
        status=status_enum,
        employee_id=employee_id,
        role_id=role_id,
        employee_ids=final_employee_ids if final_employee_ids else None,
        include_manager=include_manager,
        aggregation_level=aggregation_level_enum,
        only_active=only_active,
        show_details=show_details,
        min_hour_limit=min_hour_limit,
        max_hour_limit=max_hour_limit
    )


# ==================== MAIN ENDPOINT ====================
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.get("/manager/", response=ManagerDashboardResponseSchema)
def get_manager_dashboard(
        request,
        period: ColaboradorPeriodEnum = Query(ColaboradorPeriodEnum.MONTH),
        start_date: Optional[date] = Query(None),
        end_date: Optional[date] = Query(None),
        project_id: Optional[int] = Query(None),
        activity_id: Optional[int] = Query(None),
        status: Optional[str] = Query(None),
        employee_ids: List[int] = Query([]),
        employee_id: Optional[int] = Query(None),
        role_id: Optional[int] = Query(None),
        include_manager: bool = Query(False),
        aggregation_level: str = Query("department"),
        only_active: bool = Query(True),
        show_details: bool = Query(False),
        min_hour_limit: Optional[float] = Query(None, ge=0, le=24),
        max_hour_limit: Optional[float] = Query(None, ge=0, le=24)
):
    """
    Complete dashboard for department managers.
    Shows aggregated and individual team metrics.
    """

    try:
        # 1. Create filter schema from parameters
        filters = create_manager_filter_from_params(
            period=period,
            start_date=start_date,
            end_date=end_date,
            project_id=project_id,
            activity_id=activity_id,
            status=status,
            employee_ids=employee_ids,
            employee_id=employee_id,
            role_id=role_id,
            include_manager=include_manager,
            aggregation_level=aggregation_level,
            only_active=only_active,
            show_details=show_details,
            min_hour_limit=min_hour_limit,
            max_hour_limit=max_hour_limit
        )
    except Exception as e:
        from ninja.errors import ValidationError
        raise ValidationError([{"loc": ["query"], "msg": str(e)}])

    # 2. Get manager's department
    department = get_manager_department(request)

    # 3. Get period date range
    date_range = get_period_date_range(
        period=filters.period.type.value,
        start_date=filters.period.start_date,
        end_date=filters.period.end_date
    )

    period_start = date_range['start_date']
    period_end = date_range['end_date']
    period_label = date_range['label']

    # Adjust future dates
    today = timezone.now().date()
    if period_end > today:
        period_end = today
    if period_start > today:
        period_start = today

    # 4. Get department employees
    employees = get_department_employees(department)

    # Apply filters
    if filters.only_active:
        employees = employees.filter(is_active=True)

    if filters.employee_ids and len(filters.employee_ids) > 0:
        employees = employees.filter(id__in=filters.employee_ids)

    if filters.employee_id:
        employees = employees.filter(id=filters.employee_id)

    if filters.role_id:
        employees = employees.filter(position_id=filters.role_id)

    employee_ids_list = list(employees.values_list('id', flat=True))

    if not employee_ids_list:
        # Return empty dashboard
        empty_summary = DepartmentKPISchema(
            total_hours=Decimal('0.00'),
            daily_average_hours=0.0,
            average_hours_per_employee=0.0,
            utilization_rate=0.0,
            submission_rate=0.0,
            total_employees=len(employees),
            employees_with_records=0,
            total_projects=0,
            active_projects=0,
            worked_days=0,
            workdays=0,
            days_without_records=0
        )

        return ManagerDashboardResponseSchema(
            metadata={
                "version": "2.0",
                "timestamp": timezone.now().isoformat(),
                "processing_time": None,
                "cache": {"used": False, "key": None, "expires_at": None}
            },
            context={"origin": "manager_dashboard"},
            user={"id": request.user.id, "name": request.user.get_full_name()},
            department=DepartmentSchema(
                id=department.id,
                name=department.name,
                active_employees=len(employees)
            ),
            filters=filters.dict(),
            analysis_period={
                "start_date": period_start,
                "end_date": period_end,
                "label": period_label,
                "days": (period_end - period_start).days + 1
            },
            data={
                "summary": empty_summary,
                "project_distribution": [],
                "role_distribution": [],
                "daily_evolution": [],
                "top_employees": [],
                "recent_activities": {
                    "timesheets": [],
                    "tasks": [],
                    "approvals": [],
                    "comments": []
                }
            },
            analysis={
                "insights": ["Department has no active employees"],
                "highlights": [],
                "attention_points": [],
                "active_alerts": [],
                "risk_indicators": []
            },
            recommendations={},
            resources={},
            data_quality={
                "completeness": 0.0,
                "freshness": None,
                "sources": ["database"],
                "notes": ["No data available"]
            }
        )

    # 5. Calculate department KPIs
    kpis_dict = calculate_department_kpis(
        employee_ids_list,
        period_start,
        period_end,
        filters.project_id,
        filters.activity_id,
        filters.status.value if filters.status else None
    )

    # 6. Generate insights, alerts, and risks
    insights = generate_department_insights(kpis_dict, len(employees))
    alerts = generate_department_alerts(kpis_dict)
    risks = generate_risk_indicators(kpis_dict)

    # 7. Get employee summaries
    employee_summaries = []
    for employee in employees:
        summary = get_employee_summary(
            employee,
            period_start,
            period_end,
            filters.project_id,
            filters.activity_id,
            filters.status.value if filters.status else None
        )
        employee_summaries.append(summary)

    # Sort employees by hours (highest first)
    employee_summaries.sort(key=lambda x: float(x['total_hours']), reverse=True)

    # 8. Build response data

    # Department KPIs
    department_kpis = DepartmentKPISchema(
        total_hours=kpis_dict['total_hours'],
        daily_average_hours=(
            float(kpis_dict['total_hours']) / kpis_dict['workdays']
            if kpis_dict['workdays'] > 0 else 0
        ),
        average_hours_per_employee=kpis_dict['avg_hours_per_employee'],
        utilization_rate=kpis_dict['utilization_rate'],
        submission_rate=kpis_dict['submission_rate'],
        total_employees=kpis_dict['total_employees'],
        employees_with_records=kpis_dict['active_employee_count'],
        total_projects=len(kpis_dict['hours_by_project']),
        active_projects=len(kpis_dict['hours_by_project']),
        worked_days=kpis_dict['worked_days'],
        workdays=kpis_dict['workdays'],
        days_without_records=kpis_dict['workdays'] - (
                    kpis_dict['worked_days'] // max(1, kpis_dict['active_employee_count'])),
        efficiency_score=kpis_dict['efficiency_score'],
        productivity_score=kpis_dict['department_productivity_index']
    )

    # Top employees
    top_employees = []
    for i, emp in enumerate(employee_summaries[:10], 1):
        employee_basic = BasicEmployeeSchema(
            id=emp['id'],
            full_name=emp['full_name'],
            email=request.user.email,  # In real app, get from employee object
            role=emp['position'],
            active=True,
            department_id=department.id,
            department_name=department.name
        )

        top_employees.append(EmployeeKPISchema(
            employee=employee_basic,
            total_hours=emp['total_hours'],
            worked_days=emp['days_with_tasks'],
            daily_average_hours=emp['avg_daily_hours'],
            submission_rate=emp['submission_rate'],
            projects_worked=emp['projects_worked'],
            weekend_hours=emp['weekend_hours'],
            ranking_department=i
        ))

    # Project distribution
    project_distribution = []
    for proj in kpis_dict['hours_by_project']:
        project_schema = ProjectSchema(
            id=proj['id'],
            name=proj['name'],
            code=proj.get('code'),
            actual_hours=proj['total_hours']
        )

        project_distribution.append(ProjectDistributionSchema(
            project=project_schema,
            total_hours=proj['total_hours'],
            percentage=proj['percentage'],
            employees_involved=proj['employee_count'],
            average_hours_per_employee=(
                float(proj['total_hours']) / proj['employee_count']
                if proj['employee_count'] > 0 else 0
            )
        ))

    # Daily evolution
    daily_evolution_data = get_daily_evolution(
        employee_ids_list,
        period_start,
        period_end,
        filters.project_id,
        filters.activity_id,
        filters.status.value if filters.status else None
    )

    daily_evolution = []
    for day in daily_evolution_data:
        daily_evolution.append(DailyEvolutionSchema(
            date=day['date'],
            total_hours=day['total_hours'],
            active_employees=day['employee_count'],
            active_projects=day['project_count'],
            average_hours_per_employee=day['avg_hours'],
            day_of_week=day['day_of_week'],
            is_weekend=day['is_weekend']
        ))

    # System alerts
    system_alerts = [SystemAlertSchema(**alert) for alert in alerts]

    # Risk indicators
    risk_indicators = [RiskIndicatorSchema(**risk) for risk in risks]

    # Build final response
    return ManagerDashboardResponseSchema(
        metadata={
            "version": "2.0",
            "timestamp": timezone.now().isoformat(),
            "processing_time": None,
            "cache": {"used": False, "key": None, "expires_at": None}
        },
        context={
            "origin": "manager_dashboard",
            "request_time": timezone.now().isoformat(),
            "department_id": department.id
        },
        user={
            "id": request.user.id,
            "name": request.user.get_full_name(),
            "email": request.user.email,
            "is_manager": True
        },
        department=DepartmentSchema(
            id=department.id,
            name=department.name,
            manager_id=request.user.id,
            manager_name=request.user.get_full_name(),
            active_employees=len(employees),
            total_employees=len(employees),
            active_projects=len(kpis_dict['hours_by_project'])
        ),
        filters=filters.dict(),
        analysis_period={
            "start_date": period_start.isoformat(),
            "end_date": period_end.isoformat(),
            "label": period_label,
            "days": (period_end - period_start).days + 1,
            "is_custom": period == ColaboradorPeriodEnum.CUSTOM
        },
        data={
            "summary": department_kpis,
            "project_distribution": project_distribution,
            "role_distribution": [],  # Could be populated if role data is available
            "daily_evolution": daily_evolution,
            "top_employees": top_employees,
            "recent_activities": {
                "timesheets": [],
                "tasks": [],
                "approvals": [],
                "comments": []
            }
        },
        analysis={
            "insights": insights,
            "highlights": [
                f"Top project: {kpis_dict.get('top_project', 'N/A')} ({kpis_dict.get('top_project_percentage', 0):.1f}%)",
                f"Peak productivity: {kpis_dict.get('peak_day', 'N/A')}"
            ] if kpis_dict.get('top_project') else [],
            "attention_points": [
                f"Pending timesheets: {kpis_dict.get('pending_timesheets_count', 0)}",
                f"Weekend work: {kpis_dict.get('weekend_hours_percentage', 0):.1f}%"
            ],
            "active_alerts": system_alerts,
            "risk_indicators": risk_indicators
        },
        recommendations={
            "priority_actions": [],
            "improvement_suggestions": [],
            "metrics_to_monitor": [],
            "suggested_reports": []
        },
        resources={
            "urls": {
                "export": f"/api/dashboard/manager/export/?period={period.value}",
                "detailed_report": f"/api/reports/department/{department.id}/",
                "timesheet_management": "/timesheets/",
                "team_dashboard": "/dashboard/team/"
            },
            "visualization_options": [
                {"value": "chart", "label": "Charts"},
                {"value": "table", "label": "Tables"},
                {"value": "grid", "label": "Grid"}
            ],
            "available_widgets": [
                "kpi_summary",
                "project_distribution",
                "daily_evolution",
                "top_employees",
                "alerts"
            ],
            "system_limits": {
                "max_results": 1000,
                "max_period_days": 365,
                "cache_minutes": 5
            }
        },
        data_quality={
            "completeness": 85.0,  # Example value
            "freshness": timezone.now().isoformat(),
            "sources": ["timesheet_tasks", "timesheets", "users"],
            "notes": ["Data updated in real-time"]
        }
    )


# ==================== SPECIFIC EMPLOYEE ENDPOINT ====================
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.get("/manager/employee/{employee_id}/", response=Dict[str, Any])
def get_employee_detail(
        request,
        employee_id: int,
        period: ColaboradorPeriodEnum = Query(ColaboradorPeriodEnum.MONTH),
        start_date: Optional[date] = Query(None),
        end_date: Optional[date] = Query(None)
):
    """
    Details of a specific employee for the manager.
    Includes individual metrics and history.
    """

    # 1. Validate manager access to this employee
    department = get_manager_department(request)

    try:
        employee = User.objects.get(id=employee_id, department=department)
    except User.DoesNotExist:
        raise PermissionDenied("Employee not found or not in your department")

    # 2. Get period
    date_range = get_period_date_range(
        period=period,
        start_date=start_date,
        end_date=end_date
    )

    period_start = date_range['start_date']
    period_end = date_range['end_date']

    # 3. Get employee data
    employee_summary = get_employee_summary(employee, period_start, period_end, None, None, None)

    # 4. Get employee's tasks
    tasks_qs = Task.objects.filter(
        timesheet__employee=employee,
        created_at__gte=period_start,
        created_at__lte=period_end
    ).select_related('project', 'activity', 'timesheet')

    # 5. Get projects worked on
    employee_projects = tasks_qs.exclude(project__isnull=True).values(
        'project__id', 'project__name'
    ).annotate(
        total_hours=Sum('hour'),
        task_count=Count('id')
    ).order_by('-total_hours')[:10]

    # 6. Get recent timesheets
    recent_timesheets = Timesheet.objects.filter(
        employee=employee,
        created_at__gte=period_start,
        created_at__lte=period_end
    ).order_by('-created_at')[:10]

    timesheets_list = []
    for ts in recent_timesheets:
        days_to_submit = None
        if ts.status == 'submetido' and ts.submitted_at and ts.created_at:
            days_to_submit = (ts.submitted_at - ts.created_at).days

        timesheets_list.append({
            "id": ts.id,
            "status": ts.status,
            "total_hour": ts.total_hour,
            "created_at": ts.created_at,
            "submitted_at": ts.submitted_at,
            "days_to_submit": days_to_submit,
            "task_count": ts.tasks.count()
        })

    # 7. Build response
    return {
        "employee": {
            "id": employee.id,
            "full_name": employee.get_full_name(),
            "position": employee.position.name if employee.position else None,
            "department": department.name,
            "email": employee.email,
            "hire_date": employee.date_joined.date() if employee.date_joined else None,
            "active": employee.is_active
        },
        "period": {
            "start_date": period_start,
            "end_date": period_end,
            "days": (period_end - period_start).days + 1
        },
        "metrics": employee_summary,
        "projects": list(employee_projects),
        "recent_timesheets": timesheets_list,
        "performance_indicators": {
            "productivity_level": "high" if employee_summary['avg_daily_hours'] > 6 else "medium" if employee_summary[
                                                                                                         'avg_daily_hours'] > 4 else "low",
            "reliability": "high" if employee_summary['submission_rate'] > 90 else "medium" if employee_summary[
                                                                                                   'submission_rate'] > 70 else "low",
            "engagement": "high" if employee_summary['work_frequency'] > 80 else "medium" if employee_summary[
                                                                                                 'work_frequency'] > 60 else "low"
        }
    }


# ==================== DEPARTMENT PROJECTS ENDPOINT ====================
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.get("/manager/projects/", response=List[DepartmentProjectSchema])
def get_department_projects(
        request,
        period: ColaboradorPeriodEnum = Query(ColaboradorPeriodEnum.MONTH),
        start_date: Optional[date] = Query(None),
        end_date: Optional[date] = Query(None),
        min_percentage: Optional[float] = Query(0, ge=0, le=100)
):
    """Detailed list of department projects"""

    department = get_manager_department(request)
    employees = get_department_employees(department)
    employee_ids = list(employees.values_list('id', flat=True))

    date_range = get_period_date_range(
        period=period,
        start_date=start_date,
        end_date=end_date
    )

    period_start = date_range['start_date']
    period_end = date_range['end_date']

    # Get project statistics
    project_stats = Task.objects.filter(
        timesheet__employee__id__in=employee_ids,
        created_at__gte=period_start,
        created_at__lte=period_end
    ).exclude(project__isnull=True).values(
        'project__id', 'project__name', 'project__code'
    ).annotate(
        total_hours=Sum('hour'),
        employee_count=Count('timesheet__employee', distinct=True),
        task_count=Count('id')
    ).order_by('-total_hours')

    # Calculate department total
    total_department = Task.objects.filter(
        timesheet__employee__id__in=employee_ids,
        created_at__gte=period_start,
        created_at__lte=period_end
    ).aggregate(total=Sum('hour'))['total'] or Decimal('0.00')

    projects = []
    for proj in project_stats:
        percentage = (
            (float(proj['total_hours']) / float(total_department)) * 100
            if total_department > 0 else 0
        )

        # Filter by minimum percentage
        if percentage < min_percentage:
            continue

        # Determine trend (simplified - could be enhanced with historical data)
        trend = None
        avg_hours = (
            float(proj['total_hours']) / proj['employee_count']
            if proj['employee_count'] > 0 else 0
        )

        if avg_hours > 40:
            trend = "high"
        elif avg_hours > 20:
            trend = "medium"
        else:
            trend = "low"

        projects.append(DepartmentProjectSchema(
            id=proj['project__id'],
            name=proj['project__name'],
            total_hours=proj['total_hours'],
            employee_count=proj['employee_count'],
            avg_hours_per_employee=avg_hours,
            percentage_of_department=round(percentage, 1),
            trend=trend
        ))

    return projects


# ==================== FILTER OPTIONS ENDPOINT ====================
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.get("/manager/filter-options/", response=ManagerFilterOptionsSchema)
def get_manager_filter_options(request):
    """Return filter options for managers"""

    department = get_manager_department(request)
    employees = get_department_employees(department)

    # Employees
    employees_list = []
    for emp in employees:
        employees_list.append(BasicEmployeeSchema(
            id=emp.id,
            full_name=emp.get_full_name(),
            email=emp.email,
            role=emp.position.name if emp.position else None,
            role_id=emp.position.id if emp.position else None,
            active=emp.is_active,
            hire_date=emp.date_joined.date() if emp.date_joined else None,
            department_id=department.id,
            department_name=department.name
        ))

    # Projects used by department
    project_objs = Task.objects.filter(
        timesheet__employee__in=employees
    ).exclude(
        Q(project__isnull=True) | Q(project__name__isnull=True)
    ).values(
        'project_id', 'project__name', 'project__code'
    ).distinct().order_by('project__name')

    projects_list = []
    for p in project_objs:
        projects_list.append(ProjectSchema(
            id=p['project_id'],
            name=p['project__name'],
            code=p['project__code']
        ))

    # Department activities
    activities = Activity.objects.filter(
        department=department,
        is_active=True
    ).values('id', 'name').order_by('name')

    activities_list = [
        {"id": a['id'], "name": a['name']}
        for a in activities
    ]

    # Roles in department
    roles = employees.exclude(position__isnull=True).values(
        'position__id', 'position__name'
    ).distinct().order_by('position__name')

    roles_list = [
        {"id": r['position__id'], "name": r['position__name']}
        for r in roles
    ]

    return ManagerFilterOptionsSchema(
        employees=employees_list,
        projects=projects_list,
        activities=activities_list,
        roles=roles_list
    )