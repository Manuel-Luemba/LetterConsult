# core/dashboard/api_manager.py
from django.core.exceptions import PermissionDenied
from ninja import Router, Query
from django.db.models import Q, Sum, Count, Avg, F
from django.db.models import DecimalField
from datetime import timedelta, datetime
from django.utils import timezone
from typing import List, Optional, Dict, Any
from decimal import Decimal
import statistics

from pydantic.schema import date
from rest_framework.decorators import permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication

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
    RiskIndicatorSchema,
    PeriodComparisonSchema,
    TrendSchema,
    RecommendedActionSchema,
    ExportResponseSchema,
    ErrorResponseSchema,
    PeriodEnum,
    TimesheetStatusEnum,
    AggregationLevelEnum,
    SeverityEnum, PeriodSchema
)
from core.timesheet.models import Task, Timesheet
from core.user.models import User
from core.project.models import Project
from core.activity.models import Activity

router = Router(tags=["Manager Dashboard"])


# ==================== HELPER FUNCTIONS ====================
def get_manager_department(request):
    """Get manager's department"""
    user = request.auth or request.auth
    if not user or not user.is_authenticated:
        raise PermissionDenied("User not authenticated")

    if not user.department:
        raise PermissionDenied("Manager has no department assigned")

    return user.department


def get_department_employees(department, include_manager=False, only_active=True):
    """Get employees from department with filters"""
    queryset = User.objects.filter(department=department)

    if not include_manager:
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

    # Calculate averages
    #daily_average_hours = float(total_hours) / workdays if workdays > 0 else 0
    daily_average_hours = float(total_hours) / worked_days if worked_days > 0 else 0  # Não days_in_period
    average_hours_per_employee = float(total_hours) / total_employees if total_employees > 0 else 0

    # Calculate submission rate
    total_timesheets = timesheets_qs.count()
    submitted_timesheets = timesheets_qs.filter(status=TimesheetStatusEnum.SUBMITTED.value).count()
    submission_rate = (submitted_timesheets / total_timesheets * 100) if total_timesheets > 0 else 0

    # Calculate utilization rate (simplified)
    expected_hours = total_employees * workdays * 8  # 8 hours per day
    utilization_rate = (float(total_hours) / expected_hours * 100) if expected_hours > 0 else 0

    # Get project counts
    projects = tasks_qs.exclude(project__isnull=True).values('project').distinct()
    total_projects = projects.count()
    active_projects = total_projects  # Simplified

    # Calculate scores (simplified for now)
    efficiency_score = min(utilization_rate * 1.2, 100)
    productivity_score = min((daily_average_hours / 8) * 100, 100)

    return {
        'total_hours': total_hours,
        'daily_average_hours': daily_average_hours,
        'average_hours_per_employee': average_hours_per_employee,
        'utilization_rate': utilization_rate,
        'submission_rate': submission_rate,
        'approval_rate': None,  # Not implemented yet
        'total_employees': total_employees,
        'employees_with_records': employees_with_records,
        'total_projects': total_projects,
        'active_projects': active_projects,
        'worked_days': worked_days,
        'workdays': workdays,
        'days_without_records': days_without_records,
        'efficiency_score': efficiency_score,
        'productivity_score': productivity_score
    }


def get_project_distribution(employees_ids, start_date, end_date, filters: ManagerFilterSchema):
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

    distribution = []
    for proj in project_stats:
        percentage = (float(proj['total_hours']) / float(
            total_department_hours) * 100) if total_department_hours > 0 else 0
        avg_hours = float(proj['total_hours']) / proj['employees_involved'] if proj['employees_involved'] > 0 else 0

        project_schema = ProjectSchema(
            id=proj['project_id'],
            name=proj['project__name'],
           # code=proj['project__code'],
            actual_hours=proj['total_hours']
        )

        distribution.append(ProjectDistributionSchema(
            project=project_schema,
            total_hours=proj['total_hours'],
            percentage=percentage,
            employees_involved=proj['employees_involved'],
            average_hours_per_employee=avg_hours
        ))

    return distribution


def get_role_distribution(employees_ids, start_date, end_date, filters: ManagerFilterSchema):
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
            total_hours=role['total_hours'],
            active_employees=role['active_employees'],
            average_hours_per_role=avg_hours,
            percentage=percentage
        ))

    return distribution


def get_daily_evolution(employees_ids, start_date, end_date, filters: ManagerFilterSchema):
    """Get daily hour evolution"""

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
                total_hours=stat['total_hours'],
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
                total_hours=Decimal('0.00'),
                active_employees=0,
                active_projects=0,
                average_hours_per_employee=0,
                day_of_week=current_date.strftime('%A'),
                is_weekend=is_weekend
            ))

        current_date += timedelta(days=1)

    return evolution


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
            'hours': top_project['project_hours']
        }

    # Calculate overtime and weekend hours
    overtime_hours = Decimal('0.00')  # Simplified
    weekend_hours = tasks_qs.filter(
        created_at__week_day__in=[1, 7]  # Sunday=1, Saturday=7
    ).aggregate(total=Sum('hour'))['total'] or Decimal('0.00')

    # Create employee schema
    employee_schema = BasicEmployeeSchema(
        id=employee.id,
        full_name=employee.get_full_name(),
       # email=employee.email,
        role=employee.position.name if employee.position else None,
        role_id=employee.position.id if employee.position else None,
        active=employee.is_active,
        hire_date=employee.date_joined.date() if employee.date_joined else None,
        department_id=employee.department.id if employee.department else None,
        department_name=employee.department.name if employee.department else None
    )

    return EmployeeKPISchema(
        employee=employee_schema,
        total_hours=total_hours,
        worked_days=worked_days,
        daily_average_hours=daily_average_hours,
        submission_rate=submission_rate,
        approval_rate=None,  # Not implemented yet
        projects_worked=projects_worked,
        top_project=top_project_dict,
        overtime_hours=overtime_hours,
        weekend_hours=weekend_hours,
        department_ranking=None,  # Would need to calculate against all employees
        department_percentile=None  # Would need to calculate against all employees
    )


def get_top_employees(employees, start_date, end_date, filters: ManagerFilterSchema, limit: int = 10):
    """Get top employees by hours"""

    employee_kpis = []
    for employee in employees:
        kpi = get_employee_kpis(employee, start_date, end_date, filters, len(employees))
        employee_kpis.append(kpi)

    # Sort by total hours
    employee_kpis.sort(key=lambda x: float(x.total_hours), reverse=True)

    return employee_kpis[:limit]


def generate_insights(kpis: DepartmentKPISchema, employees_count: int, start_date, end_date) -> List[str]:
    """Generate insights based on KPIs"""

    insights = []

    # Utilization insights
    if kpis.utilization_rate > 90:
        insights.append("🚀 High utilization rate: Team is working at optimal capacity")
    elif kpis.utilization_rate < 50:
        insights.append("📉 Low utilization rate: Consider allocating more work or projects")
    else:
        insights.append(f"📊 Normal utilization: {kpis.utilization_rate:.1f}% of capacity")

    # Submission rate insights
    if kpis.submission_rate == 100:
        insights.append("✅ All timesheets submitted on time")
    elif kpis.submission_rate > 80:
        insights.append(f"📝 Good submission rate: {kpis.submission_rate:.1f}%")
    else:
        insights.append(f"⚠️  Low submission rate: {kpis.submission_rate:.1f}% - Follow up with team")

    # Productivity insights
    if kpis.daily_average_hours > 7:
        insights.append(f"⚡ High productivity: {kpis.daily_average_hours:.1f}h average per day")
    elif kpis.daily_average_hours < 4:
        insights.append(f"🐌 Low productivity: {kpis.daily_average_hours:.1f}h average per day")

    # Work pattern insights
    if kpis.days_without_records > (kpis.workdays * 0.3):  # 30% days without records
        insights.append(f"📅 {kpis.days_without_records} days without records - check team availability")

    # Employee participation insights
    participation_rate = (kpis.employees_with_records / kpis.total_employees * 100) if kpis.total_employees > 0 else 0
    if participation_rate < 80:
        insights.append(f"👥 Low team participation: {participation_rate:.1f}% of team has records")

    return insights[:5]  # Limit to 5 insights


def generate_alerts(kpis: DepartmentKPISchema, filters: ManagerFilterSchema) -> List[SystemAlertSchema]:
    """Generate system alerts"""

    alerts = []
    now = timezone.now()

    # Low submission rate alert
    if kpis.submission_rate < 70:
        alerts.append(SystemAlertSchema(
            id=f"alert_submission_{now.timestamp()}",
            type="warning",
            title="Low Timesheet Submission Rate",
            description=f"Only {kpis.submission_rate:.1f}% of timesheets have been submitted",
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
            title="High Team Utilization",
            description=f"Team is at {kpis.utilization_rate:.1f}% utilization - risk of burnout",
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
            title="No Activity Records",
            description="No team members have recorded hours in this period",
            priority=SeverityEnum.HIGH,
            creation_date=now,
            action_required=True,
            read=False
        ))

    return alerts


# ==================== MAIN ENDPOINTS ====================
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.get("/manager/", response=ManagerDashboardResponseSchema)
def get_manager_dashboard(request, filters: ManagerFilterSchema = Query(...)):
    """
    Complete manager dashboard with comprehensive analytics
    """

    try:
        # 1. Get manager's department
        department = get_manager_department(request)

        # 2. Get period dates
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

        # 3. Get department employees
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

        # 4. Calculate KPIs
        kpis_dict = calculate_department_kpis(employee_ids, start_date, end_date, filters)
        kpis = DepartmentKPISchema(**kpis_dict)

        # 5. Get distributions
        project_distribution = get_project_distribution(employee_ids, start_date, end_date, filters)
        role_distribution = get_role_distribution(employee_ids, start_date, end_date, filters)
        daily_evolution = get_daily_evolution(employee_ids, start_date, end_date, filters)

        # 6. Get top employees
        top_employees = get_top_employees(employees, start_date, end_date, filters, limit=5)

        # 7. Get specific employee if requested
        specific_employee = None
        if filters.employee_id and filters.aggregation_level == AggregationLevelEnum.INDIVIDUAL:
            try:
                employee = employees.get(id=filters.employee_id)
                specific_employee = get_employee_kpis(employee, start_date, end_date, filters, len(employees))
            except User.DoesNotExist:
                pass

        # 8. Generate insights and alerts
        insights = generate_insights(kpis, len(employees), start_date, end_date)
        alerts = generate_alerts(kpis, filters)

        # 9. Build department schema
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

        # 10. Build response
        return ManagerDashboardResponseSchema(
            metadata={
                "version": "2.0",
                "timestamp": timezone.now().isoformat(),
                "processing_time": None,
                "cache": {
                    "used": False,
                    "key": None,
                    "expires_at": None
                }
            },
            context={
                "source": "manager_dashboard",
                "user_id": request.auth.id,
                "department_id": department.id,
                "filter_level": filters.aggregation_level.value
            },
            user={
                "id": request.auth.id,
                "username": request.auth.username,
                "email": request.auth.email,
                "is_manager": True
            },
            department=department_schema,
            filters=filters,
            analysis_period={
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "days": (end_date - start_date).days + 1,
                "label": date_range['label']
            },
            data={
                "summary": kpis,
                "project_distribution": project_distribution[:10],  # Limit to 10
                "role_distribution": role_distribution,
                "daily_evolution": daily_evolution,
                "top_employees": top_employees,
                "specific_employee": specific_employee,
                "complete_ranking": None,  # Could be implemented
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

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error in manager dashboard: {str(e)}", exc_info=True)

        # Return error in the schema format
        return ManagerDashboardResponseSchema(
            metadata={
                "version": "2.0",
                "timestamp": timezone.now().isoformat(),
                "error": str(e)
            },
            context={"error": True},
            user={"id": request.auth.id if request.auth else None},
            department={},
            filters=filters if 'filters' in locals() else {},
            analysis_period={},
            data={},
            analysis={
                "active_alerts": [],
                "risk_indicators": [],
                "insights": [f"Error loading dashboard: {str(e)}"],
                "highlights": [],
                "attention_points": []
            },
            recommendations={},
            resources={},
            data_quality={"completeness": 0.0, "freshness": None, "sources": [], "notes": ["Error occurred"]}
        )


@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.get("/manager/filter-options/", response=ManagerFilterOptionsSchema)
def get_manager_filter_options(request):
    """Get available filter options for manager dashboard"""

    try:
        department = get_manager_department(request)

        # Get employees
        employees = get_department_employees(department, only_active=True)
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
                #code=proj['project__code'],
                actual_hours=actual_hours
            ))

        # Get activities
        activities = Activity.objects.filter(
            department=department,
            is_active=True
        ).values('id', 'name', 'code').order_by('name')

        activities_list = []
        for act in activities:
            activities_list.append({
                "id": act['id'],
                "name": act['name'],
                "code": act['code'],
                "billable": True  # Default
            })

        # # Get roles
        # roles = Role.objects.filter(
        #     users__in=employees
        # ).distinct().values('id', 'name').order_by('name')
        #
        # roles_list = []
        # for role in roles:
        #     roles_list.append({
        #         "id": role['id'],
        #         "name": role['name'],
        #         "description": f"Role in {department.name}"
        #     })

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

        # Return minimal options on error
        return ManagerFilterOptionsSchema(
            projects=[],
            activities=[],
            employees=[],
            roles=[]
        )


@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.get("/manager/employee/{employee_id}/", response=Dict[str, Any])
def get_employee_detail(
        request,
        employee_id: int,
        period: PeriodEnum = Query(PeriodEnum.MONTH),
        start_date: Optional[date] = Query(None),
        end_date: Optional[date] = Query(None)
):
    """Get detailed analytics for a specific employee"""

    try:
        # Verify access
        department = get_manager_department(request)

        try:
            employee = User.objects.get(id=employee_id, department=department)
        except User.DoesNotExist:
            return ErrorResponseSchema(
                error="employee_not_found",
                code="EMPLOYEE_NOT_FOUND",
                message="Employee not found or not in your department",
                timestamp=timezone.now()
            )

        # Get period
        date_range = get_period_date_range(period, start_date, end_date)
        period_start = date_range['start_date']
        period_end = date_range['end_date']

        # Create filters for this employee
        filters = ManagerFilterSchema(
            period=PeriodSchema(type=period, start_date=period_start, end_date=period_end),
            aggregation_level=AggregationLevelEnum.INDIVIDUAL
        )

        # Get employee KPIs
        department_employees = get_department_employees(department)
        employee_kpi = get_employee_kpis(employee, period_start, period_end, filters, len(department_employees))

        # Get detailed tasks
        tasks_qs = Task.objects.filter(
            timesheet__employee=employee,
            created_at__gte=period_start,
            created_at__lte=period_end
        ).select_related('project', 'activity', 'timesheet')

        # Get project breakdown
        project_breakdown = tasks_qs.exclude(project__isnull=True).values(
            'project__id', 'project__name'
        ).annotate(
            total_hours=Sum('hour'),
            task_count=Count('id'),
            avg_hours_per_day=Avg('hour')
        ).order_by('-total_hours')

        # Get daily breakdown
        daily_breakdown = tasks_qs.values('created_at').annotate(
            daily_hours=Sum('hour'),
            task_count=Count('id')
        ).order_by('created_at')

        # Get timesheet history
        timesheets = Timesheet.objects.filter(
            employee=employee,
            created_at__gte=period_start,
            created_at__lte=period_end
        ).order_by('-created_at')[:10]

        timesheet_history = []
        for ts in timesheets:
            days_to_submit = None
            if ts.status == TimesheetStatusEnum.SUBMITTED.value and ts.submitted_at and ts.created_at:
                days_to_submit = (ts.submitted_at.date() - ts.created_at.date()).days

            timesheet_history.append({
                "id": ts.id,
                "status": ts.status,
                "total_hours": ts.total_hour,
                "created_at": ts.created_at,
                "submitted_at": ts.submitted_at,
                "days_to_submit": days_to_submit
            })

        return {
            "employee": {
                "id": employee.id,
                "full_name": employee.get_full_name(),
                "email": employee.email,
                "role": employee.position.name if employee.position else None,
                "department": department.name,
                "hire_date": employee.date_joined.date() if employee.date_joined else None,
                "active": employee.is_active
            },
            "period": {
                "start_date": period_start,
                "end_date": period_end,
                "days": (period_end - period_start).days + 1
            },
            "kpis": employee_kpi.dict(),
            "project_breakdown": list(project_breakdown),
            "daily_breakdown": list(daily_breakdown),
            "timesheet_history": timesheet_history,
            "insights": [
                f"Worked {float(employee_kpi.total_hours):.1f} hours in period",
                f"Daily average: {employee_kpi.daily_average_hours:.1f} hours",
                f"Submission rate: {employee_kpi.submission_rate:.1f}%",
                f"Projects worked on: {employee_kpi.projects_worked}"
            ]
        }

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error getting employee detail: {str(e)}", exc_info=True)

        return ErrorResponseSchema(
            error="server_error",
            code="SERVER_ERROR",
            message=f"Error loading employee details: {str(e)}",
            timestamp=timezone.now()
        )


@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.get("/manager/project/{project_id}/", response=Dict[str, Any])
def get_project_analytics(
        request,
        project_id: int,
        period: PeriodEnum = Query(PeriodEnum.MONTH),
        start_date: Optional[date] = Query(None),
        end_date: Optional[date] = Query(None)
):
    """Get detailed analytics for a specific project"""

    try:
        department = get_manager_department(request)

        # Verify project exists and is accessible
        try:
            project = Project.objects.get(id=project_id)
        except Project.DoesNotExist:
            return ErrorResponseSchema(
                error="project_not_found",
                code="PROJECT_NOT_FOUND",
                message="Project not found",
                timestamp=timezone.now()
            )

        # Get period
        date_range = get_period_date_range(period, start_date, end_date)
        period_start = date_range['start_date']
        period_end = date_range['end_date']

        # Get department employees
        employees = get_department_employees(department)
        employee_ids = list(employees.values_list('id', flat=True))

        # Get project tasks
        tasks_qs = Task.objects.filter(
            project_id=project_id,
            timesheet__employee_id__in=employee_ids,
            created_at__gte=period_start,
            created_at__lte=period_end
        ).select_related('timesheet__employee', 'activity')

        # Calculate project metrics
        total_hours_result = tasks_qs.aggregate(
            total=Sum('hour', output_field=DecimalField(max_digits=10, decimal_places=2))
        )
        total_hours = total_hours_result['total'] or Decimal('0.00')

        # Get employee participation
        employee_participation = tasks_qs.values(
            'timesheet__employee_id',
            'timesheet__employee__first_name',
            'timesheet__employee__last_name',
            'timesheet__employee__position__name'
        ).annotate(
            employee_hours=Sum('hour'),
            days_worked=Count('created_at', distinct=True)
        ).order_by('-employee_hours')

        # Get activity breakdown
        activity_breakdown = tasks_qs.values(
            'activity_id', 'activity__name'
        ).annotate(
            activity_hours=Sum('hour')
        ).order_by('-activity_hours')

        # Get daily progress
        daily_progress = tasks_qs.values('created_at').annotate(
            daily_hours=Sum('hour')
        ).order_by('created_at')

        # Calculate cumulative hours
        cumulative_hours = Decimal('0.00')
        daily_progress_list = []
        for day in daily_progress:
            cumulative_hours += day['daily_hours'] or Decimal('0.00')
            daily_progress_list.append({
                "date": day['created_at'],
                "hours": float(day['daily_hours'] or 0),
                "cumulative_hours": float(cumulative_hours)
            })

        return {
            "project": {
                "id": project.id,
                "name": project.name,
                "code": project.code,
                "description": project.description,
                "start_date": project.start_date,
                "end_date": project.end_date,
                "budgeted_hours": float(project.budgeted_hours) if project.budgeted_hours else None
            },
            "analytics": {
                "total_hours": float(total_hours),
                "employee_count": employee_participation.count(),
                "activity_count": activity_breakdown.count(),
                "days_active": len(daily_progress_list),
                "average_daily_hours": float(total_hours) / len(daily_progress_list) if daily_progress_list else 0,
                "budget_utilization": (
                        float(total_hours) / float(project.budgeted_hours) * 100
                ) if project.budgeted_hours and float(project.budgeted_hours) > 0 else None
            },
            "employee_participation": [
                {
                    "employee_id": emp['timesheet__employee_id'],
                    "employee_name": f"{emp['timesheet__employee__first_name']} {emp['timesheet__employee__last_name']}",
                    "role": emp['timesheet__employee__position__name'],
                    "hours": float(emp['employee_hours'] or 0),
                    "percentage": (
                                float(emp['employee_hours'] or 0) / float(total_hours) * 100) if total_hours > 0 else 0,
                    "days_worked": emp['days_worked']
                }
                for emp in employee_participation
            ],
            "activity_breakdown": [
                {
                    "activity_id": act['activity_id'],
                    "activity_name": act['activity__name'],
                    "hours": float(act['activity_hours'] or 0),
                    "percentage": (
                                float(act['activity_hours'] or 0) / float(total_hours) * 100) if total_hours > 0 else 0
                }
                for act in activity_breakdown
            ],
            "daily_progress": daily_progress_list,
            "period": {
                "start_date": period_start,
                "end_date": period_end,
                "label": date_range['label']
            }
        }

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error getting project analytics: {str(e)}", exc_info=True)

        return ErrorResponseSchema(
            error="server_error",
            code="SERVER_ERROR",
            message=f"Error loading project analytics: {str(e)}",
            timestamp=timezone.now()
        )


@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.get("/manager/export/", response=ExportResponseSchema)
def export_dashboard_data(
        request,
        start_date: date,
        end_date: date,
        format: str = "excel",
        include_details: bool = False
):
    """Export dashboard data"""

    try:
        department = get_manager_department(request)

        # Generate filename
        timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
        filename = f"dashboard_export_{department.name}_{timestamp}.{format}"

        # In production, you would:
        # 1. Generate the actual file
        # 2. Upload to storage
        # 3. Return the actual URL

        return ExportResponseSchema(
            download_url=f"/api/exports/{filename}",
            filename=filename,
            format=format,
            size_bytes=1024 * 100,  # Mock size
            expires_at=timezone.now() + timedelta(hours=24),
            export_parameters={
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "department_id": department.id,
                "include_details": include_details,
                "format": format
            }
        )

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error exporting data: {str(e)}", exc_info=True)

        return ErrorResponseSchema(
            error="export_error",
            code="EXPORT_ERROR",
            message=f"Error exporting data: {str(e)}",
            timestamp=timezone.now()
        )


@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.get("/manager/alerts/", response=List[SystemAlertSchema])
def get_manager_alerts(request, unread_only: bool = True):
    """Get alerts and notifications for manager"""

    try:
        department = get_manager_department(request)
        now = timezone.now()

        # Mock alerts - in production, get from database
        alerts = [
            SystemAlertSchema(
                id="alert_001",
                type="warning",
                title="Low Timesheet Submission",
                description=f"Timesheet submission rate in {department.name} is below 80%",
                priority=SeverityEnum.MEDIUM,
                creation_date=now - timedelta(days=1),
                action_required=True,
                action_url="/manager/timesheets/pending",
                read=False
            ),
            SystemAlertSchema(
                id="alert_002",
                type="info",
                title="New Project Assigned",
                description=f"Your department has been assigned to project 'Management System'",
                priority=SeverityEnum.LOW,
                creation_date=now - timedelta(hours=3),
                action_required=False,
                read=False
            )
        ]

        if unread_only:
            alerts = [alert for alert in alerts if not alert.read]

        return alerts

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error getting alerts: {str(e)}", exc_info=True)
        return []


@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.post("/manager/alerts/{alert_id}/read/")
def mark_alert_as_read(request, alert_id: str):
    """Mark alert as read"""

    try:
        # In production, update in database
        return {
            "success": True,
            "message": f"Alert {alert_id} marked as read",
            "timestamp": timezone.now().isoformat()
        }

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error marking alert as read: {str(e)}", exc_info=True)

        return {
            "success": False,
            "message": f"Error: {str(e)}",
            "timestamp": timezone.now().isoformat()
        }


@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.get("/manager/quick-stats/", response=Dict[str, Any])
def get_quick_stats(request):
    """Get quick statistics for dashboard (optimized for speed)"""

    try:
        department = get_manager_department(request)

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

        return ErrorResponseSchema(
            error="stats_error",
            code="STATS_ERROR",
            message=f"Error loading statistics: {str(e)}",
            timestamp=timezone.now()
        )


@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.get("/manager/health/", response=Dict[str, Any])
def dashboard_health_check(request):
    """Health check for dashboard services"""

    try:
        department = get_manager_department(request)

        # Check database connectivity
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            db_healthy = cursor.fetchone()[0] == 1

        # Check recent data
        recent_tasks = Task.objects.filter(
            created_at__gte=timezone.now().date() - timedelta(days=7)
        ).exists()

        # Check employee data
        employees = get_department_employees(department, only_active=True)
        employee_count = employees.count()

        return {
            "status": "healthy",
            "timestamp": timezone.now().isoformat(),
            "checks": {
                "database": db_healthy,
                "recent_data": recent_tasks,
                "employee_data": employee_count > 0,
                "user_permissions": request.auth.has_perm('user.view_department')
            },
            "department": {
                "id": department.id,
                "name": department.name,
                "employee_count": employee_count
            },
            "version": "2.0",
            "environment": "production"
        }

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Health check failed: {str(e)}", exc_info=True)

        return {
            "status": "unhealthy",
            "timestamp": timezone.now().isoformat(),
            "error": str(e),
            "checks": {
                "database": False,
                "recent_data": False,
                "employee_data": False,
                "user_permissions": False
            }
        }