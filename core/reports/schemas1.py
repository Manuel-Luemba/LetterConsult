# core/dashboard/schemas_coordenador.py
from ninja import Schema
from typing import List, Dict, Any, Optional
from decimal import Decimal
from pydantic import Field, validator, root_validator
from datetime import date
from django.utils import timezone
from pydantic.schema import datetime

from .schemas_colaborador import DashboardFilterSchema


# ==================== FILTROS COORDENADOR ====================
class CoordenadorFilterSchema(DashboardFilterSchema):
    """Filtros estendidos para coordenadores"""
    employee_ids: List[int] = Field(default_factory=list, description="Filtrar por colaboradores específicos")
    show_only_pending: Optional[bool] = Field(default=False, description="Mostrar apenas pendentes")
    compare_period: Optional[bool] = Field(default=False, description="Comparar com período anterior")

    @root_validator(skip_on_failure=True)
    def validate_coordenador_filters(cls, values):
        """Validações específicas para coordenadores"""
        period = values.get("period")
        employee_ids = values.get("employee_ids")

        # Se filtrar por colaborador, não pode mostrar comparativo entre todos
        if employee_ids and len(employee_ids) > 0 and values.get("compare_period"):
            raise ValueError("Não é possível comparar períodos quando filtra por colaboradores específicos")

        return values


# ==================== DADOS DE COLABORADOR INDIVIDUAL ====================
class ColaboradorResumoSchema(Schema):
    """Resumo de um colaborador para listagem"""
    id: int
    full_name: str
    position: Optional[str]
    total_hours: Decimal = Field(default=Decimal('0.00'))
    avg_daily_hours: float = Field(default=0.0)
    work_frequency: float = Field(default=0.0)
    submitted_timesheets: int = Field(default=0)
    pending_timesheets: int = Field(default=0)
    submission_rate: float = Field(default=0.0)
    last_activity: Optional[date] = None
    status: str = Field(default="ativo")  # ativo, inativo, alerta

    @validator('work_frequency', 'submission_rate')
    def validate_percentages(cls, v):
        if v is not None and (v < 0 or v > 100):
            raise ValueError(f"Porcentagem deve estar entre 0 e 100: {v}")
        return round(v, 1) if v is not None else v


# ==================== PROJETO DO DEPARTAMENTO ====================
class DepartamentoProjectSchema(Schema):
    """Projeto com métricas do departamento"""
    id: int
    name: str
    total_hours: Decimal
    colaborador_count: int  # Quantos colaboradores trabalharam no projeto
    avg_hours_per_colaborador: float
    percentage_of_department: float
    trend: Optional[str] = None  # up, down, stable


# ==================== TIMESHEET PENDENTE ====================
class TimesheetPendenteSchema(Schema):
    """Timesheet pendente de atenção"""
    id: int
    employee_name: str
    employee_id: int
    created_at: date
    days_since_creation: int
    total_hours: Decimal
    task_count: int
    last_modified: Optional[date] = None


# ==================== KPIs DO DEPARTAMENTO ====================
class DepartamentoKPISchema(Schema):
    """KPIs agregados do departamento"""

    # SEÇÃO 1: PRODUTIVIDADE GERAL
    total_hours: Decimal
    avg_hours_per_colaborador: float
    colaborador_count: int
    active_colaborador_count: int  # Com registros no período
    department_productivity_index: float  # Índice personalizado

    # SEÇÃO 2: DISTRIBUIÇÃO
    hours_by_project: List[Dict[str, Any]] = Field(default_factory=list)
    top_project: Optional[str] = None
    top_project_percentage: Optional[float] = None
    project_concentration: float #% em  top 3 projetos

    # SEÇÃO 3: COMPORTAMENTOS
    weekend_hours: Decimal = Field(default=Decimal('0.00'))
    weekend_hours_percentage: float = Field(default=0.0)
    overload_days: int = Field(default=0)  # Dias com >8h no departamento
    max_consecutive_work_days: int = Field(default=0)

    # SEÇÃO 4: QUALIDADE DE REGISTROS
    submission_rate: float # % de timesheets submetidos
    avg_days_to_submit: Optional[float] = None
    pending_timesheets_count: int
    pending_timesheets_oldest_days: Optional[int] = None

    # SEÇÃO 5: EQUILÍBRIO DE CARGA
    load_balance_index: float  # Quão equilibrada está a carga (0-100)
    top_colaborador_hours: Optional[Decimal] = None
    bottom_colaborador_hours: Optional[Decimal] = None
    hours_std_dev: Optional[float] = None  # Desvio padrão das horas

    # SEÇÃO 6: TENDÊNCIAS
    trend_vs_previous: Optional[float] = None # % de variação vs período anterior
    peak_day: Optional[str] = None
    peak_day_hours: Optional[Decimal] = None

    # SEÇÃO 7: METADADOS
    period_label: str
    insights: List[str] = Field(default_factory=list)
    alerts: List[str] = Field(default_factory=list)


# ==================== EVOLUÇÃO TEMPORAL ====================
class EvolucaoTemporalSchema(Schema):
    """Dados para gráfico de evolução"""
    date: date
    total_hours: Decimal
    colaborador_count: int
    avg_hours: float


# ==================== COMPARATIVO ENTRE COLABORADORES ====================
class ComparativoColaboradorSchema(Schema):
    """Dados para comparativo entre colaboradores"""
    metric: str
    values: List[float]
    labels: List[str]
    avg_value: float
    top_performer: Optional[str] = None
    needs_attention: Optional[str] = None


# ==================== RESPOSTA COMPLETA COORDENADOR ====================
class CoordenadorDashboardResponseSchema(Schema):
    """Resposta completa do dashboard do coordenador"""
    kpis: DepartamentoKPISchema
    colaboradores: List[ColaboradorResumoSchema]
    projetos: List[DepartamentoProjectSchema]
    evolucao_temporal: List[EvolucaoTemporalSchema]
    timesheets_pendentes: List[TimesheetPendenteSchema]
    comparativos: Dict[str, ComparativoColaboradorSchema]
    filters_applied: CoordenadorFilterSchema
    date_range: Dict[str, date]
    generated_at: datetime = Field(default_factory=timezone.now)


# ==================== OPÇÕES DE FILTRO COORDENADOR ====================
class CoordenadorFilterOptionsSchema(Schema):
    """Opções de filtro para coordenadores"""
    colaboradores: List[Dict[str, Any]]
    projects: List[Dict[str, Any]]
    activities: List[Dict[str, Any]]
    status_options: List[Dict[str, str]]
    period_options: List[Dict[str, str]]