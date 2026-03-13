from enum import Enum

from ninja import Schema
from datetime import date
from typing import List, Optional, Dict, Any
from decimal import Decimal

from ninja.errors import ValidationError
from pydantic import Field
from pydantic.schema import timedelta
from django.utils import timezone

# ============================================
# SCHEMAS
# ============================================


class TaskSimpleSchema(Schema):
    id: int
    project_name: Optional[str]
    activity_name: Optional[str]
    hour: Decimal
    created_at: date

class TimesheetSimpleSchema(Schema):
    id: int
    status: str
    total_hour: Decimal
    created_at: date
    submitted_at: Optional[date]
    updated_at: Optional[date] = None  # Mudado de datetime para date
    obs: Optional[str] = None
    employee_name: Optional[str] = None
    department_name: Optional[str] = None

class DailyHoursSchema(Schema):
    date: date
    total_hours: Decimal

class ProjectHoursSchema(Schema):
    project_name: str
    total_hours: Decimal
    percentage: float

class ColaboradorKPISchema(Schema):
    total_hours_period: Decimal = Field(..., description="Total de horas no período selecionado")
    total_hours_week: Decimal = Field(..., description="Total de horas na semana atual")
    pending_timesheets: int = Field(..., description="Timesheets pendentes (rascunho)")
    submitted_timesheets: int = Field(..., description="Timesheets submetidos")
    avg_daily_hours: float = Field(..., description="Média diária de horas")

class ColaboradorDashboardSchema(Schema):
    kpis: ColaboradorKPISchema
    daily_hours: List[DailyHoursSchema]
    project_hours: List[ProjectHoursSchema]
    recent_tasks: List[TaskSimpleSchema]
    recent_timesheets: List[TimesheetSimpleSchema]


class PeriodEnum(str, Enum):
    TODAY = "today"
    YESTERDAY = "yesterday"
    WEEK = "week"
    MONTH = "month"
    QUARTER = "quarter"
    YEAR = "year"
    LAST_WEEK = "last_week"
    LAST_MONTH = "last_month"
    CUSTOM = "custom"

class DashboardFilterSchema(Schema):
    """Schema para filtros do dashboard"""
    period: PeriodEnum = Field(default=PeriodEnum.MONTH, description="Período de análise")
    start_date: Optional[date] = Field(default=None, description="Data inicial (para period='custom')")
    end_date: Optional[date] = Field(default=None, description="Data final (para period='custom')")
    project_id: Optional[int] = Field(default=None, description="Filtrar por projeto específico")
    activity_id: Optional[int] = Field(default=None, description="Filtrar por atividade específica")
    status: Optional[str] = Field(default=None, description="Filtrar por status do timesheet")

    group_by: Optional[str] = "project"  # project, activity, client, status, day, week, month

    def get_date_range(self) -> dict:
        """Calcula o range de datas baseado no período selecionado"""
        hoje = timezone.now().date()

        if self.period == PeriodEnum.TODAY:
            start = end = hoje
        elif self.period == PeriodEnum.YESTERDAY:
            start = end = hoje - timedelta(days=1)
        elif self.period == PeriodEnum.WEEK:
            start = hoje - timedelta(days=hoje.weekday())  # Segunda-feira
            end = hoje
        elif self.period == PeriodEnum.LAST_WEEK:
            start = hoje - timedelta(days=hoje.weekday() + 7)
            end = start + timedelta(days=6)
        elif self.period == PeriodEnum.MONTH:
            start = hoje.replace(day=1)
            end = hoje
        elif self.period == PeriodEnum.LAST_MONTH:
            if hoje.month == 1:
                start = date(hoje.year - 1, 12, 1)
            else:
                start = date(hoje.year, hoje.month - 1, 1)
            end = (start.replace(month=start.month % 12 + 1, year=start.year + (start.month // 12))
                   - timedelta(days=1))
        elif self.period == PeriodEnum.QUARTER:
            quarter = (hoje.month - 1) // 3 + 1
            start = date(hoje.year, 3 * quarter - 2, 1)
            end = hoje
        elif self.period == PeriodEnum.YEAR:
            start = date(hoje.year, 1, 1)
            end = hoje
        elif self.period == PeriodEnum.CUSTOM and self.start_date and self.end_date:
            start = self.start_date
            end = self.end_date
        else:
            # Default: este mês
            start = hoje.replace(day=1)
            end = hoje

        return {"start_date": start, "end_date": end}


    # def get_date_range(self) -> Dict[str, date]:
    #     """Calcula o intervalo de datas baseado no período selecionado"""
    #     hoje = timezone.now().date()
    #
    #     # PRIORIDADE 1: Se datas personalizadas foram fornecidas, usá-las
    #     if self.start_date and self.end_date:
    #         print(f"[DEBUG] Usando datas personalizadas: {self.start_date} a {self.end_date}")
    #         return {"start_date": self.start_date, "end_date": self.end_date}
    #
    #     # PRIORIDADE 2: Calcular baseado no período
    #     if self.period == PeriodEnum.WEEK:
    #         inicio_periodo = hoje - timedelta(days=hoje.weekday())
    #         fim_periodo = hoje
    #
    #     elif self.period == PeriodEnum.MONTH:
    #         inicio_periodo = hoje.replace(day=1)
    #         fim_periodo = hoje
    #
    #     elif self.period == PeriodEnum.QUARTER:
    #         current_quarter = (hoje.month - 1) // 3 + 1
    #         inicio_periodo = date(hoje.year, 3 * current_quarter - 2, 1)
    #         fim_periodo = hoje
    #
    #     elif self.period == PeriodEnum.YEAR:
    #         inicio_periodo = date(hoje.year, 1, 1)
    #         fim_periodo = hoje
    #
    #     elif self.period == PeriodEnum.CUSTOM and self.start_date and self.end_date:
    #         inicio_periodo = self.start_date
    #         fim_periodo = self.end_date
    #     else:
    #         # Fallback para mês atual
    #         inicio_periodo = hoje.replace(day=1)
    #         fim_periodo = hoje
    #
    #     return {"start_date": inicio_periodo, "end_date": fim_periodo}


    def get_date_range(self) -> Dict[str, date]:
        """Calcula o intervalo de datas baseado no período selecionado"""
        hoje = timezone.now().date()

        if self.period == PeriodEnum.WEEK:
            inicio_periodo = hoje - timedelta(days=hoje.weekday())
            fim_periodo = hoje

        elif self.period == PeriodEnum.MONTH:
            inicio_periodo = hoje.replace(day=1)
            fim_periodo = hoje

        elif self.period == PeriodEnum.QUARTER:
            current_quarter = (hoje.month - 1) // 3 + 1
            inicio_periodo = date(hoje.year, 3 * current_quarter - 2, 1)
            fim_periodo = hoje

        elif self.period == PeriodEnum.YEAR:
            inicio_periodo = date(hoje.year, 1, 1)
            fim_periodo = hoje

        elif self.period == PeriodEnum.CUSTOM:
            if self.start_date and self.end_date:
                # Validação: end_date não pode ser anterior a start_date
                if self.end_date < self.start_date:
                    raise ValidationError("end_date não pode ser anterior a start_date")

                # Validação: datas não podem ser futuras (opcional)
                if self.start_date > hoje or self.end_date > hoje:
                    print(f"[AVISO] Datas futuras selecionadas: {self.start_date} a {self.end_date}")

                inicio_periodo = self.start_date
                fim_periodo = self.end_date
            else:
                # CUSTOM sem datas especificadas - fallback para mês atual
                print(f"[AVISO] Período CUSTOM sem datas, usando mês atual")
                inicio_periodo = hoje.replace(day=1)
                fim_periodo = hoje
        else:
            # Fallback para mês atual
            inicio_periodo = hoje.replace(day=1)
            fim_periodo = hoje

        print(f"[DEBUG] Período: {self.period}, Data range: {inicio_periodo} a {fim_periodo}")
        return {"start_date": inicio_periodo, "end_date": fim_periodo}


class FilteredDashboardResponseSchema(ColaboradorDashboardSchema):
    filters_applied: DashboardFilterSchema
    date_range: Dict[str, date]  # Para mostrar o intervalo usado

class FilterOptionsSchema(Schema):
    projects: List[Dict[str, Any]]
    activities: List[Dict[str, Any]]
    status_options: List[Dict[str, str]]
    period_options: List[Dict[str, str]]
