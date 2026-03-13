# utils/periods.py
from datetime import date, timedelta, timezone
from typing import Dict, Any
from enum import Enum
from django.utils import timezone

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


def get_period_date_range(
        period: PeriodEnum,
        start_date: date = None,
        end_date: date = None
) -> Dict[str, Any]:
    """
    Retorna o intervalo de datas para um período específico.
    Inclui datas e metadados para exibição.
    """
    hoje = timezone.now().date()

    # Mapeamento completo de períodos
    if period == PeriodEnum.TODAY:
        start = hoje
        end = hoje
        label = "Hoje"

    elif period == PeriodEnum.YESTERDAY:
        start = hoje - timedelta(days=1)
        end = start
        label = "Ontem"

    elif period == PeriodEnum.WEEK:
        start = hoje - timedelta(days=hoje.weekday())  # Segunda-feira
        end = hoje
        label = "Esta Semana"

    elif period == PeriodEnum.LAST_WEEK:
        start = hoje - timedelta(days=hoje.weekday() + 7)  # Segunda da semana passada
        end = start + timedelta(days=6)  # Domingo da semana passada
        label = "Semana Passada"

    elif period == PeriodEnum.MONTH:
        start = hoje.replace(day=1)
        end = hoje
        label = f"Este Mês ({start.strftime('%B')})"

    elif period == PeriodEnum.LAST_MONTH:
        primeiro_dia_mes_atual = hoje.replace(day=1)
        ultimo_dia_mes_anterior = primeiro_dia_mes_atual - timedelta(days=1)
        start = ultimo_dia_mes_anterior.replace(day=1)
        end = ultimo_dia_mes_anterior
        label = f"Mês Passado ({start.strftime('%B')})"

    elif period == PeriodEnum.QUARTER:
        current_quarter = (hoje.month - 1) // 3 + 1
        start = date(hoje.year, 3 * current_quarter - 2, 1)
        end = hoje
        label = f"T{current_quarter} {hoje.year}"

    elif period == PeriodEnum.YEAR:
        start = date(hoje.year, 1, 1)
        end = hoje
        label = str(hoje.year)

    elif period == PeriodEnum.CUSTOM:
        if start_date and end_date:
            start = start_date
            end = end_date
            label = "Personalizado"
        else:
            # Fallback para mês atual
            start = hoje.replace(day=1)
            end = hoje
            label = "Este Mês (fallback)"
    else:
        # Fallback padrão
        start = hoje.replace(day=1)
        end = hoje
        label = "Este Mês"

    # Calcular diferença de dias
    days_diff = (end - start).days + 1

    print(days_diff, 'diferencia de dias ')

    return {
        "start_date": start,
        "end_date": end,
        "label": label,
        "days_count": days_diff,
        "is_today": period == PeriodEnum.TODAY,
        "is_week": period in [PeriodEnum.WEEK, PeriodEnum.LAST_WEEK],
        "is_month": period in [PeriodEnum.MONTH, PeriodEnum.LAST_MONTH],
    }


def get_period_options() -> list:
    """Retorna opções de período para frontend"""
    return [
        {"value": PeriodEnum.TODAY, "label": "Hoje", "icon": "calendar-day"},
        {"value": PeriodEnum.YESTERDAY, "label": "Ontem", "icon": "calendar-day"},
        {"value": PeriodEnum.WEEK, "label": "Esta Semana", "icon": "calendar-week"},
        {"value": PeriodEnum.LAST_WEEK, "label": "Semana Passada", "icon": "calendar-week"},
        {"value": PeriodEnum.MONTH, "label": "Este Mês", "icon": "calendar"},
        {"value": PeriodEnum.LAST_MONTH, "label": "Mês Passado", "icon": "calendar"},
        {"value": PeriodEnum.QUARTER, "label": "Este Trimestre", "icon": "chart-pie"},
        {"value": PeriodEnum.YEAR, "label": "Este Ano", "icon": "calendar-alt"},
        {"value": PeriodEnum.CUSTOM, "label": "Personalizado", "icon": "calendar-edit"},
    ]