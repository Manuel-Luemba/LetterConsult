"""
COMPLETE SCHEMAS FOR MANAGER DASHBOARD
Unified and comprehensive structure
"""

from ninja import Schema
from typing import List, Dict, Any, Optional, Union
from decimal import Decimal
from pydantic import Field, validator
from datetime import date, datetime
from django.utils import timezone
from enum import Enum


# ==================== ENUMS AND CONSTANTS ====================
class PeriodEnum(str, Enum):
    TODAY = "today"
    YESTERDAY = "yesterday"
    WEEK = "week"
    LAST_WEEK = "last_week"
    MONTH = "month"
    LAST_MONTH = "last_month"
    QUARTER = "quarter"
    YEAR = "year"
    CUSTOM = "custom"


class TimesheetStatusEnum(str, Enum):
    DRAFT = "rascunho"
    SUBMITTED = "submetido"
    # APPROVED = "approved"
    # REJECTED = "rejected"

# ==================== DEPARTMENT PROJECT ====================
class DepartmentProjectSchema(Schema):
    """Project with department metrics"""
    id: int
    name: str
    total_hours: Decimal
    employee_count: int  # How many employees worked on the project
    avg_hours_per_employee: float
    percentage_of_department: float
    trend: Optional[str] = None  # up, down, stable


class AggregationLevelEnum(str, Enum):
    DEPARTMENT = "department"
    INDIVIDUAL = "individual"
    ROLE = "role"
    PROJECT = "project"


class SeverityEnum(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# ==================== FILTERS ====================
class PeriodSchema(Schema):
    """Temporal period definition"""
    type: PeriodEnum = Field(default=PeriodEnum.MONTH)
    start_date: Optional[date] = None
    end_date: Optional[date] = None

    @validator('end_date')
    def validate_dates(cls, v, values):
        if v and values.get('start_date') and v < values['start_date']:
            raise ValueError('End date must be after start date')
        return v


class DashboardBaseFilterSchema(Schema):
    """Base filters for all dashboards"""
    period: PeriodSchema = Field(default_factory=lambda: PeriodSchema())
    project_id: Optional[int] = None
    activity_id: Optional[int] = None
    status: Optional[TimesheetStatusEnum] = None


class ManagerFilterSchema(DashboardBaseFilterSchema):
    """Specific filters for managers"""
    employee_id: Optional[int] = Field(
        None,
        description="Specific employee ID (from the manager's department)"
    )
    role_id: Optional[int] = Field(
        None,
        description="Filter by specific role"
    )
    employee_ids: Optional[List[int]] = Field(
        None,
        description="List of employee IDs"
    )
    include_manager: bool = Field(
        False,
        description="Include the manager's own data"
    )
    aggregation_level: AggregationLevelEnum = Field(
        AggregationLevelEnum.DEPARTMENT,
        description="Data aggregation level"
    )
    only_active: bool = Field(
        True,
        description="Only active employees"
    )
    show_details: bool = Field(
        False,
        description="Show detailed data"
    )
    min_hour_limit: Optional[float] = Field(
        None,
        ge=0,
        le=24,
        description="Filter by minimum daily average"
    )
    max_hour_limit: Optional[float] = Field(
        None,
        ge=0,
        le=24,
        description="Filter by maximum daily average"
    )


# ==================== BASIC ENTITIES ====================
class BasicEmployeeSchema(Schema):
    """Basic employee information"""
    id: int
    full_name: str = Field(..., alias="full_name")
    username: Optional[str] = None
    #email: str
    role: Optional[str] = None
    role_id: Optional[int] = None
    active: bool = True
    hire_date: Optional[date] = None
    avatar_url: Optional[str] = None
    department_id: int
    department_name: str

    @validator('full_name', pre=True)
    def build_full_name(cls, v, values):
        if isinstance(v, dict):
            first_name = v.get('first_name', '')
            last_name = v.get('last_name', '')
            return f"{first_name} {last_name}".strip()
        return v


class DepartmentSchema(Schema):
    """Complete department information"""
    id: int
    name: str
    acronym: Optional[str] = None
    description: Optional[str] = None
    manager_id: Optional[int] = None
    manager_name: Optional[str] = None
    utilization_target: Optional[float] = Field(75.0, ge=0, le=100)
    efficiency_target: Optional[float] = Field(80.0, ge=0, le=100)
    active_employees: int = 0
    total_employees: int = 0
    active_projects: int = 0


class ProjectSchema(Schema):
    """Basic project information"""
    id: int
    name: str
    code: Optional[str] = None
    client: Optional[str] = None
    budgeted_hours: Optional[Decimal] = None
    actual_hours: Decimal = Decimal('0.00')
    completion_percentage: Optional[float] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None


# ==================== KPIs AND METRICS ====================
class KPIBaseSchema(Schema):
    """Base for all KPIs"""
    value: Union[Decimal, int, float]
    unit: str
    description: str
    comparison: Optional[Dict[str, Any]] = None
    trend: Optional[str] = None  # 'positive', 'negative', 'neutral'


class DepartmentKPISchema(Schema):
    """Main department KPIs"""
    # Hours
    total_hours: Decimal = Field(..., description="Total worked hours")
    daily_average_hours: float = Field(..., description="Average hours per workday")
    average_hours_per_employee: float = Field(..., description="Average hours per employee")

    # Rates
    utilization_rate: float = Field(..., ge=0, le=100, description="Utilization percentage")
    submission_rate: float = Field(..., ge=0, le=100, description="Timesheet submission percentage")
    approval_rate: Optional[float] = Field(None, ge=0, le=100, description="Approval percentage")

    # Counts
    total_employees: int
    employees_with_records: int
    total_projects: int
    active_projects: int

    # Time
    worked_days: int
    workdays: int
    days_without_records: int

    # Scores
    efficiency_score: Optional[float] = Field(None, ge=0, le=100)
    productivity_score: Optional[float] = Field(None, ge=0, le=100)


class EmployeeKPISchema(Schema):
    """KPIs for a specific employee"""
    employee: BasicEmployeeSchema
    total_hours: Decimal
    worked_days: int
    daily_average_hours: float
    submission_rate: float
    approval_rate: Optional[float] = None
    projects_worked: int
    top_project: Optional[Dict[str, Any]] = None
    overtime_hours: Decimal = Decimal('0.00')
    weekend_hours: Decimal = Decimal('0.00')
    department_ranking: Optional[int] = None
    department_percentile: Optional[float] = None


# ==================== DISTRIBUTIONS AND GROUPINGS ====================
class ProjectDistributionSchema(Schema):
    """Hour distribution by project"""
    project: ProjectSchema
    total_hours: Decimal
    percentage: float
    employees_involved: int
    average_hours_per_employee: float
    completion_percentage: Optional[float] = None


class RoleDistributionSchema(Schema):
    """Hour distribution by role"""
    role_id: int
    role_name: str
    total_hours: Decimal
    active_employees: int
    average_hours_per_role: float
    percentage: float


class DailyEvolutionSchema(Schema):
    """Hour evolution by day"""
    date: date
    total_hours: Decimal
    active_employees: int
    active_projects: int
    average_hours_per_employee: float
    day_of_week: str
    is_holiday: bool = False
    is_weekend: bool = False


# ==================== ALERTS AND INDICATORS ====================
class RiskIndicatorSchema(Schema):
    """Identified risk indicator"""
    type: str  # 'overload', 'underutilization', 'submission_delay', 'low_productivity'
    severity: SeverityEnum
    title: str
    description: str
    affected_employees: List[str]
    affected_count: int
    suggested_action: str
    detection_date: datetime = Field(default_factory=timezone.now)


class SystemAlertSchema(Schema):
    """System alert for the manager"""
    id: str
    type: str  # 'info', 'warning', 'critical'
    title: str
    description: str
    priority: SeverityEnum
    creation_date: datetime
    expiration_date: Optional[datetime] = None
    action_required: bool = False
    action_url: Optional[str] = None
    read: bool = False


# ==================== COMPARISONS AND TRENDS ====================
class PeriodComparisonSchema(Schema):
    """Comparison between periods"""
    current_period: Dict[str, Any]
    previous_period: Dict[str, Any]
    percentage_variation: Dict[str, float]
    highlights: List[str]
    attention_points: List[str]
    compared_days: int
    reliability: float = Field(..., ge=0, le=100)


class TrendSchema(Schema):
    """Trend over time"""
    period: str
    start_date: date
    end_date: date
    metric: str
    values: List[float]
    labels: List[str]
    overall_trend: str  # 'increasing', 'decreasing', 'stable'
    variation_rate: Optional[float] = None


# ==================== RECOMMENDATIONS AND ACTIONS ====================
class RecommendedActionSchema(Schema):
    """Recommended action for the manager"""
    id: str
    priority: SeverityEnum
    category: str  # 'people_management', 'project_allocation', 'processes', 'reports'
    title: str
    description: str
    rationale: str
    steps: List[str]
    expected_impact: str
    estimated_effort: str  # 'low', 'medium', 'high'
    suggested_deadline: Optional[date] = None
    related_url: Optional[str] = None


# ==================== MAIN RESPONSE ====================
class ManagerDashboardResponseSchema(Schema):
    """
    Complete and unified Manager Dashboard Response
    Hierarchical and organized structure
    """

    # ===== METADATA =====
    metadata: Dict[str, Any] = Field(default_factory=lambda: {
        "version": "2.0",
        "timestamp": timezone.now().isoformat(),
        "processing_time": None,
        "cache": {
            "used": False,
            "key": None,
            "expires_at": None
        }
    })

    # ===== CONTEXT AND FILTERS =====
    context: Dict[str, Any] = Field(..., description="Request context")
    user: Dict[str, Any]
    department: DepartmentSchema
    filters: ManagerFilterSchema

    # ===== ANALYZED PERIOD =====
    analysis_period: Dict[str, Any] = Field(..., description="Analyzed period")

    # ===== MAIN DATA =====
    data: Dict[str, Any] = Field(..., description="Main dashboard data")

    class MainData(Schema):
        # Aggregated summary
        summary: DepartmentKPISchema

        # Detailed views
        project_distribution: List[ProjectDistributionSchema]
        role_distribution: List[RoleDistributionSchema]
        daily_evolution: List[DailyEvolutionSchema]

        # Individual performance
        top_employees: List[EmployeeKPISchema]
        specific_employee: Optional[EmployeeKPISchema] = None
        complete_ranking: Optional[List[EmployeeKPISchema]] = None

        # Recent activities
        recent_activities: Dict[str, List[Dict[str, Any]]] = Field(default_factory=lambda: {
            "timesheets": [],
            "tasks": [],
            "approvals": [],
            "comments": []
        })

    # ===== ANALYSIS AND INSIGHTS =====
    analysis: Dict[str, Any] = Field(default_factory=lambda: {}, description="Analyses and insights")

    class DetailedAnalysis(Schema):
        # Comparisons
        period_comparison: Optional[PeriodComparisonSchema] = None
        trends: Optional[List[TrendSchema]] = None

        # Alerts and risks
        active_alerts: List[SystemAlertSchema]
        risk_indicators: List[RiskIndicatorSchema]

        # Generated insights
        insights: List[str]
        highlights: List[str]
        attention_points: List[str]

        # Benchmarking (if applicable)
        benchmark: Optional[Dict[str, Any]] = None

    # ===== RECOMMENDATIONS =====
    recommendations: Dict[str, Any] = Field(default_factory=lambda: {}, description="Recommendations")

    class DetailedRecommendations(Schema):
        priority_actions: List[RecommendedActionSchema]
        improvement_suggestions: List[str]
        metrics_to_monitor: List[Dict[str, Any]]
        suggested_reports: List[Dict[str, Any]]

    # ===== ADDITIONAL RESOURCES =====
    resources: Dict[str, Any] = Field(default_factory=lambda: {}, description="Additional resources")

    class AdditionalResources(Schema):
        urls: Dict[str, str] = Field(default_factory=lambda: {
            "export": None,
            "detailed_report": None,
            "timesheet_management": None,
            "team_dashboard": None
        })
        visualization_options: List[Dict[str, Any]]
        available_widgets: List[Dict[str, Any]]
        system_limits: Dict[str, Any] = Field(default_factory=lambda: {
            "max_results": 1000,
            "max_period_days": 365,
            "cache_minutes": 5
        })

    # ===== VALIDATION AND QUALITY =====
    data_quality: Dict[str, Any] = Field(default_factory=lambda: {
        "completeness": 0.0,
        "freshness": None,
        "sources": [],
        "notes": []
    })

    # Custom validation
    @validator('data')
    def validate_main_data(cls, v):
        if not v.get('summary'):
            raise ValueError('KPI summary is required')
        return v

    class Config:
        # Allow extra fields for compatibility with existing API
        extra = "allow"


# ==================== AUXILIARY SCHEMAS ====================
class ManagerFilterOptionsSchema(Schema):
    """Available filter options for managers"""
    projects: List[ProjectSchema]
    activities: List[Dict[str, Any]]
    employees: List[BasicEmployeeSchema]
    roles: List[Dict[str, Any]]
    periods: List[Dict[str, str]] = Field(default_factory=lambda: [
        {"value": "today", "label": "Today"},
        {"value": "yesterday", "label": "Yesterday"},
        {"value": "week", "label": "This Week"},
        {"value": "last_week", "label": "Last Week"},
        {"value": "month", "label": "This Month"},
        {"value": "last_month", "label": "Last Month"},
        {"value": "quarter", "label": "This Quarter"},
        {"value": "year", "label": "This Year"},
        {"value": "custom", "label": "Custom"}
    ])
    timesheet_statuses: List[Dict[str, str]] = Field(default_factory=lambda: [
        {"value": "draft", "label": "Draft"},
        {"value": "submitted", "label": "Submitted"},
        {"value": "approved", "label": "Approved"},
        {"value": "rejected", "label": "Rejected"}
    ])
    aggregation_levels: List[Dict[str, str]] = Field(default_factory=lambda: [
        {"value": "department", "label": "Department"},
        {"value": "individual", "label": "Individual"},
        {"value": "role", "label": "Role"},
        {"value": "project", "label": "Project"}
    ])


class DashboardConfigurationSchema(Schema):
    """Personalized dashboard settings"""
    user_id: int
    preferred_layout: str = "default"
    active_widgets: List[str] = Field(default_factory=lambda: [
        "kpi_summary",
        "project_distribution",
        "daily_evolution",
        "top_employees"
    ])
    refresh_intervals: int = 300  # seconds
    show_alerts: bool = True
    show_recommendations: bool = True
    dark_mode: bool = False
    custom_columns: Optional[Dict[str, List[str]]] = None
    favorite_projects: Optional[List[int]] = None
    priority_metrics: List[str] = Field(default_factory=lambda: [
        "utilization_rate",
        "submission_rate",
        "efficiency_score"
    ])


# ==================== SPECIFIC RESPONSES ====================
class ExportResponseSchema(Schema):
    """Response for data export"""
    download_url: str
    filename: str
    format: str  # 'excel', 'csv', 'pdf'
    size_bytes: Optional[int] = None
    expires_at: datetime
    export_parameters: Dict[str, Any]


class ErrorResponseSchema(Schema):
    """Standardized error response"""
    error: str
    code: str
    message: str
    details: Optional[Dict[str, Any]] = None
    timestamp: datetime = Field(default_factory=timezone.now)
    suggestion: Optional[str] = None
    documentation_url: Optional[str] = None