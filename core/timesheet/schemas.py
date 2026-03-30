# core/timesheet/schemas.py
from datetime import date
from ninja import Schema, ModelSchema
from pydantic import Field, ConfigDict, BaseModel
from .models import  Task
from ..erp.models import Department
from datetime import datetime
from typing import List, Optional



class DepartmentOut(ModelSchema):
    class Meta:
        model = Department
        fields = "__all__"

class TaskIn(Schema):
    id: Optional[int] = None
    project_id: int
    activity_id: int
    hour: int
    created_at: date

class TaskOut(Schema):
    id: int
    project_name: Optional[str] = None
    activity_name: Optional[str] = None
    hour: float
    created_at: date
    status: Optional[str] = None
    review_comment: Optional[str] = None
    timesheet_id: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)

    @staticmethod
    def resolve_project_name(obj):
        return getattr(obj, 'project_name', "N/A")

    @staticmethod
    def resolve_activity_name(obj):
        return getattr(obj, 'activity_name', "N/A")

class TaskViewSchema(Schema):
    id: int
    created_at: str
    project_name: str
    activity_name: str
    hour: float
    description: Optional[str] = None
    status: Optional[str] = None
    review_comment: Optional[str] = None

class TimesheetIn(Schema):
    employee_id: int
    department_id: int
    status: str
    validation_level: str = Field(default="strict")
    obs: Optional[str] = None
    tasks: List[TaskIn]
    created_at: Optional[date] = None
    force_confirm: Optional[bool] = False
    deleted_task_ids: Optional[List[int]] = None

class TimesheetOut(Schema):
    id: int
    employee_id: int
    employee_name: str
    department_id: int
    status: str
    obs: Optional[str] = None
    total_hour: float = None
    created_at: Optional[date] = None
    submitted_name: Optional[str] = None
    submitted_at: Optional[date] = None
    updated_at: Optional[date] = None
    locked_by_name: Optional[str] = None
    locked_at: Optional[datetime] = None
    tasks: List[TaskOut] = []
    tasks_count: Optional[int] = 0
    warnings: Optional[List[str]] = None
    daily_totals: Optional[dict] = None
    can_edit: Optional[bool] = False
    can_add_task: Optional[bool] = False

    model_config = ConfigDict(from_attributes=True)

class TaskUpdateIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: Optional[int] = None
    activity: int
    project: int
    hour: float = Field(..., gt=0, le=24, description="Horas devem ser entre 0 e 24")
    created_at: date

class TimesheetUpdateIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    employee_id: Optional[int] = None
    obs: Optional[str] = None
    status: Optional[str] = None
    tasks: List[TaskUpdateIn]
    created_at: Optional[date] = None
    force_confirm: bool = False
    deleted_task_ids: Optional[List[int]] = None

class PaginatedTimesheetResponse(Schema):
    count: int
    total_pages: int
    current_page: int
    page_size: int
    has_next: bool
    has_prev: bool
    items: List[TimesheetOut]

class ProjectBreakdownSchema(Schema):
    name: str
    hours: float
    color: Optional[str] = None

class HoursByProjectSchema(Schema):
    project: str
    hours: float
    color: Optional[str] = None

class DailyHoursSchema(Schema):
    date: str
    hours: float

class CommentSchema(Schema):
    id: int
    author_name: str
    content: str
    created_at: datetime

class StatusHistorySchema(Schema):
    status: str
    changed_at: datetime
    changed_by: str
    notes: Optional[str] = None

class TimesheetViewSchema(Schema):
    id: int
    employee_name: str
    department_name: str
    status: str
    submitted_at: Optional[date] = None
    locked_by_name: Optional[str] = None
    locked_at: Optional[datetime] = None
    total_hours: float
    work_days: int
    task_count: int
    daily_average: float
    obs: Optional[str] = None
    tasks: List[TaskViewSchema] = []
    hours_by_project: List[HoursByProjectSchema] = []
    daily_hours: List[DailyHoursSchema] = []
    project_breakdown: List[ProjectBreakdownSchema] = []
    status_history: List[StatusHistorySchema] = []
    comments: List[CommentSchema] = []

class CommentCreateSchema(Schema):
    content: str

class TimesheetActionSchema(Schema):
    notes: Optional[str] = None

class TaskActionIn(Schema):
    task_id: int
    status: str
    review_comment: Optional[str] = None

class TimesheetReviewIn(Schema):
    notes: Optional[str] = None
    tasks: Optional[List[TaskActionIn]] = []

class ExportResponseSchema(Schema):
    file_url: str
    file_name: str
    message: str

class ExportRequest(Schema):
    timesheet_ids: list[int]
    format: str = "excel"

class TimesheetStatsCommon(Schema):
    total_hours_month: float = 0.0
    pending_count: int = 0
    approved_count: int = 0
    rejected_count: int = 0
    submission_rate: float = 0.0

class TimesheetStatsManager(Schema):
    pending_my_approval: int = 0
    approved_by_me_count: int = 0
    avg_approval_time: float = 0.0
    total_hours_approved: float = 0.0

class TimesheetDashboardStats(Schema):
    common: Optional[TimesheetStatsCommon] = None
    manager: Optional[TimesheetStatsManager] = None

