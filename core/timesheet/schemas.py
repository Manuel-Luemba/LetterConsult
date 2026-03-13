# core/timesheet/schemas.py
from datetime import date
from ninja import Schema, ModelSchema
from pydantic import Field
from pydantic.main import BaseModel
from .models import  Task
from ..erp.models import Department
from datetime import datetime
from typing import List, Optional



class DepartmentOut(ModelSchema):
    class Config:
        model = Department
        model_fields = "__all__"
        #model_fields = ['id', 'name']

class TaskIn(Schema):
    id: Optional[int] = None  # ⚠️ ADICIONAR ESTE CAMPO
    project_id: int
    activity_id: int
    hour: int
    created_at: date

class TaskOut(ModelSchema):
    class Config:
        model = Task
        model_fields = ['id', 'timesheet', 'project', 'activity', 'hour', 'created_at', 'updated_at']

class TaskViewSchema(Schema):
    id: int
    created_at: str
    project_name: str
    activity_name: str
    hour: float
    description: Optional[str] = None

class TimesheetIn(Schema):
    employee_id: int
    department_id: int
    status: str
    validation_level: str = Field(default="strict")  # ← novo campo
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
    tasks: List[TaskOut] = []
    tasks_count: Optional[int] = 0
    warnings: Optional[List[str]] = None
    daily_totals: Optional[dict] = None
    can_edit: Optional[bool] = False
    can_add_task: Optional[bool] = False


    class Config:
        from_attributes = True
        orm_mode = True

class TaskUpdateIn(BaseModel):
    id: Optional[int] = None  # Para tasks existentes
    activity: int
    project: int
    hour: float = Field(..., gt=0, le=24, description="Horas devem ser entre 0 e 24")
    created_at: date

class TimesheetUpdateIn(BaseModel):
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
    # Informações básicas
    id: int
    employee_name: str
    department_name: str
    status: str
    #period: str
    submitted_at: datetime

    # Métricas
    total_hours: float
    work_days: int
    task_count: int
    daily_average: float

    # Conteúdo
    obs: Optional[str] = None
    tasks: List[TaskViewSchema] = []

    # Analytics
    hours_by_project: List[HoursByProjectSchema] = []
    daily_hours: List[DailyHoursSchema] = []
    project_breakdown: List[ProjectBreakdownSchema] = []

    # Histórico e comentários
    status_history: List[StatusHistorySchema] = []
    comments: List[CommentSchema] = []

class CommentCreateSchema(Schema):
    content: str

class TimesheetActionSchema(Schema):
    notes: Optional[str] = None


class ExportResponseSchema(Schema):
    file_url: str
    file_name: str
    message: str

class ExportRequest(Schema):
    timesheet_ids: list[int]
    format: str = "excel"

# class WeeklyHours(Schema):
#     week_start: date
#     week_end: date
#     total_hours: float