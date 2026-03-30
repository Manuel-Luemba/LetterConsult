from ninja import Schema
from typing import List, Dict, Any
from decimal import Decimal
from pydantic import BaseModel, Field, validator, root_validator
from typing import Optional
from datetime import date
from django.utils import timezone
from datetime import datetime
from core.reports.schemas_colaborador import PeriodEnum

# ==================== FILTROS ====================
class DashboardFilterSchema(BaseModel):
    period: PeriodEnum = Field(default=PeriodEnum.MONTH)
    start_date: Optional[date] = Field(default=None)
    end_date: Optional[date] = Field(default=None)
    project_id: Optional[int] = Field(default=None)
    activity_id: Optional[int] = Field(default=None)
    status: Optional[str] = Field(default=None)

    @validator("start_date", "end_date")
    def validate_dates_not_future(cls, v):
        """Valida que datas não sejam futuras - validação simples e independente"""
        if v and v > date.today():
            raise ValueError(f"Data não pode ser futura")
        return v

    @root_validator(skip_on_failure=True)
    def validate_period_dates(cls, values):
        """Valida lógica entre datas e período"""
        period = values.get("period")
        start_date = values.get("start_date")
        end_date = values.get("end_date")

        # Para período customizado, ambas as datas são obrigatórias
        if period == PeriodEnum.CUSTOM:
            if not start_date or not end_date:
                raise ValueError("Para período personalizado, ambas as datas são obrigatórias")

        # Para outros períodos, datas são opcionais
        # Se fornecidas, devem ser válidas
        if start_date and end_date and start_date > end_date:
            raise ValueError("Data inicial não pode ser posterior à data final")

        return values

# ==================== DADOS VISUAIS ====================
class TaskSimpleSchema(Schema):
    id: int
    project_name: Optional[str]
    activity_name: Optional[str]
    hour: Decimal
    created_at: date
    timesheet_status: Optional[str] = None

class TimesheetSimpleSchema(Schema):
    id: int
    status: str
    total_hour: Decimal
    created_at: date
    submitted_at: Optional[date]
    days_to_submit: Optional[int] = None
    employee_name: Optional[str] = None

class DailyHoursSchema(Schema):
    date: date
    total_hours: Decimal
    day_name: str
    is_weekend: bool = False

class ProjectHoursSchema(Schema):
    project_name: str
    total_hours: Decimal
    percentage: float
    task_count: int
    color: Optional[str] = None

# ==================== KPIs ====================
class ColaboradorKPISchema(Schema):
    """KPIs focados no autoacompanhamento do colaborador"""

    # SECÇÃO 1: PRODUTIVIDADE
    total_hours: Decimal
    avg_daily_hours: float
    days_in_period: int
    days_with_tasks: int
    work_frequency: float  # % de dias com trabalho

    # SECÇÃO 2: EFICIÊNCIA
    days_with_overwork: int = Field(default=0)  # Dias com > 8h
    max_consecutive_work_days: int = Field(default=0)  # Maior sequência de dias com trabalho
    weekend_hours: Decimal = Field(default=Decimal('0.00'))  # Horas em fins de semana
    weekend_work_days: int = Field(default=0)  # Dias de fim de semana com trabalho

    # SECÇÃO 3: DISCIPLINA NO TIMESHEET
    pending_timesheets: int
    submitted_timesheets: int
    submission_rate: float  # % de timesheets submetidos
    avg_days_to_submit: Optional[float] = None

    # SECÇÃO 4: DISTRIBUIÇÃO
    top_project: Optional[str] = None
    top_project_hours: Optional[Decimal] = None
    top_project_percentage: Optional[float] = None

    # SECÇÃO 5: PADRÕES
    most_productive_day: Optional[str] = None
    avg_hours_per_task: Optional[float] = None
    max_hours_in_day: Optional[Decimal] = None

    # SECÇÃO 6: METADADOS
    period_label: str
    insights: List[str] = Field(default_factory=list)

    @validator('work_frequency', 'submission_rate')
    def validate_percentages(cls, v):
        if v is not None and (v < 0 or v > 100):
            raise ValueError(f"Porcentagem deve estar entre 0 e 100: {v}")
        return round(v, 1) if v is not None else v

# ==================== RESPOSTA COMPLETA ====================
class DashboardResponseSchema(Schema):
    """Resposta completa do dashboard"""
    kpis: ColaboradorKPISchema
    daily_hours: List[DailyHoursSchema]
    project_hours: List[ProjectHoursSchema]
    recent_tasks: List[TaskSimpleSchema]
    recent_timesheets: List[TimesheetSimpleSchema]
    filters_applied: DashboardFilterSchema
    date_range: Dict[str, date]
    generated_at: datetime = Field(default_factory=timezone.now)

# ==================== OPÇÕES DE FILTRO ====================
class FilterOptionsSchema(Schema):
    projects: List[Dict[str, Any]]
    activities: List[Dict[str, Any]]
    status_options: List[Dict[str, str]]
    period_options: List[Dict[str, str]]
