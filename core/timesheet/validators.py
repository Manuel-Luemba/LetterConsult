# core/timesheet/validators.py
from collections import defaultdict
from decimal import Decimal
from typing import Optional, Tuple, Dict, List
from datetime import date, timedelta
from django.utils import timezone
from django.db.models import Sum, Q
from ninja.errors import HttpError
from django.shortcuts import get_object_or_404

from core.erp.models import Department
from core.timesheet.models import Activity, Project, Timesheet, Task
from core.user.models import User


def field_error(field: str, message: str):
    """Retorna erro estruturado por campo"""
    return HttpError(400, {field: [message]})


class TimesheetValidator:
    # CONSTANTES DE VALIDAÇÃO
    MAX_HOURS_PER_TASK = Decimal('16.00')  # Máximo por tarefa individual
    MAX_HOURS_PER_DAY = Decimal('16.00')  # Máximo por dia por colaborador (APENAS NA MESMA TIMESHEET)
    MAX_RETROACTIVE_DAYS = 30  # Máximo de dias para registrar tarefas passadas
    MIN_HOURS_PER_DAY = Decimal('0.00')  # Mínimo por tarefa

    STATUS_DISPLAY = {
        'rascunho': 'RASCUNHO',
        'submetido': 'SUBMETIDO',
    }

    @staticmethod
    def validate_timesheet_data(
            data: dict,
            timesheet_id: Optional[int] = None,
            employee_id: Optional[int] = None
    ) -> Tuple[bool, Dict, List[str]]:
        """
        Valida todos os aspectos de uma timesheet com a NOVA REGRA:
        "Entre duas timesheets diferentes não pode haver tarefas com as mesmas datas"
        """
        daily_totals = defaultdict(Decimal)
        daily_warnings = defaultdict(list)
        all_warnings = []

        validation_level = data.get("validation_level", "strict")
        force_confirm = data.get("force_confirm", False)

        try:
            # 1. VALIDAÇÕES BÁSICAS (sempre obrigatórias)
            TimesheetValidator._validate_basic_data(data, timesheet_id, employee_id)

            # Obter dados importantes
            timesheet_date = data.get('created_at')
            emp_id = data.get('employee_id', employee_id)

            # 2. ✅ NOVA REGRA: VALIDAR SOBREPOSIÇÃO DE DATAS ENTRE TIMESHEETS
            if emp_id:
                task_dates = [task['created_at'] for task in data.get('tasks', [])]
                TimesheetValidator._validate_no_date_overlap(
                    employee_id=emp_id,
                    task_dates=task_dates,
                    exclude_timesheet_id=timesheet_id,
                    context="criação" if not timesheet_id else "atualização"
                )

            # 3. VALIDAÇÃO POR TAREFA (dentro da mesma timesheet)
            task_combinations = set()

            for task_data in data.get('tasks', []):
                task_date = task_data['created_at']
                task_hour = Decimal(str(task_data['hour']))

                # Acumular para total diário (APENAS nesta timesheet)
                daily_totals[task_date] += task_hour

                # Validação individual da tarefa
                TimesheetValidator._validate_task(task_data, validation_level)

                # Validação temporal
                if timesheet_date:
                    TimesheetValidator._validate_temporal_consistency(
                        timesheet_date, task_date, emp_id
                    )

                # Validação retroativa
                TimesheetValidator._validate_retroactive_date(task_date)

                # ✅ REMOVIDO: Validação de duplicidade ENTRE timesheets
                # (agora coberta pela regra geral de não sobreposição)

                # Validação de duplicidade DENTRO da timesheet
                task_combination = (
                    task_date,
                    task_data['project_id'],
                    task_data['activity_id']
                )

                if task_combination in task_combinations:
                    activity = get_object_or_404(Activity, id=task_data['activity_id'])
                    project = get_object_or_404(Project, id=task_data['project_id'])
                    raise field_error(
                        "tasks",
                        f"Tarefa duplicada: dia {task_date}, projeto '{project.name}', atividade '{activity.name}'"
                    )
                task_combinations.add(task_combination)

                # ⚠️ Warning para tarefa longa (apenas se não for force_confirm)
                if not force_confirm and task_hour > Decimal('8.00'):
                    warning_msg = f"Tarefa de {task_hour}h excede 8 horas no dia {task_date}"
                    daily_warnings[task_date].append(warning_msg)

            # 4. ✅ VALIDAÇÃO SIMPLIFICADA: Total diário APENAS nesta timesheet
            # NÃO precisa mais validar entre timesheets diferentes!
            for task_date, total_in_this_timesheet in daily_totals.items():
                # Validar limite máximo diário (APENAS nesta timesheet)
                if total_in_this_timesheet > TimesheetValidator.MAX_HOURS_PER_DAY:
                    raise field_error(
                        "tasks",
                        f"Total diário em {task_date} é {float(total_in_this_timesheet)}h "
                        f"(máximo permitido: {TimesheetValidator.MAX_HOURS_PER_DAY}h)"
                    )

                # AVISOS OPCIONAIS (apenas se não for force_confirm)
                if not force_confirm:
                    if total_in_this_timesheet > Decimal('8.00'):
                        warning_msg = (
                            f"⚠️ Total de horas no dia {task_date} é {float(total_in_this_timesheet)}h "
                            f"(superior às 8h normais). Deseja confirmar?"
                        )
                        daily_warnings[task_date].append(warning_msg)
                    elif total_in_this_timesheet < Decimal('8.00'):
                        warning_msg = (
                            f"⚠️ Total de horas no dia {task_date} é {float(total_in_this_timesheet)}h "
                            f"(mínimo recomendado: 8h). Deseja confirmar?"
                        )
                        daily_warnings[task_date].append(warning_msg)

            # 5. Validação de duplicidade de timesheet na mesma data
            if validation_level == "strict":
                TimesheetValidator._validate_duplicate_timesheet(
                    data, timesheet_id, employee_id
                )

            # 6. COLETAR AVISOS
            if not force_confirm:
                for warnings in daily_warnings.values():
                    all_warnings.extend(warnings)

            return True, dict(daily_totals), all_warnings

        except HttpError:
            raise
        except Exception as e:
            raise HttpError(500, f"Erro na validação: {str(e)}")

    # ==================== NOVA FUNÇÃO PRINCIPAL ====================

    @staticmethod
    def _validate_no_date_overlap(
            employee_id: int,
            task_dates: List[date],
            exclude_timesheet_id: Optional[int] = None,
            context: str = "criação"
    ) -> None:
        """
        REGRA SIMPLES E CLARA
        """
        if not task_dates:
            return

        # Buscar datas já ocupadas
        occupied_dates = Task.objects.filter(
            timesheet__employee_id=employee_id,
            created_at__in=task_dates
        ).values_list('created_at', flat=True).distinct()

        if exclude_timesheet_id:
            occupied_dates = occupied_dates.exclude(timesheet_id=exclude_timesheet_id)

        if not occupied_dates.exists():
            return

        # Formatar datas
        dates_list = sorted([d.strftime("%d/%m/%Y") for d in occupied_dates])

        if len(dates_list) == 1:
            raise field_error(
                "tasks",
                f"A data {dates_list[0]} já está ocupada em outra timesheet. "
                f"Escolha uma data diferente."
            )
        else:
            dates_str = ", ".join(dates_list)
            raise field_error(
                "tasks",
                f"As datas {dates_str} já estão ocupadas em outras timesheets. "
                f"Escolha datas diferentes."
            )
    # ==================== MÉTODOS AUXILIARES (SIMPLIFICADOS) ====================

    @staticmethod
    def _get_aggregated_daily_total(
            employee_id: int,
            task_date: date,
            exclude_timesheet_id: Optional[int],
            new_hours: Decimal
    ) -> Decimal:
        """
        ✅ MANTIDO para compatibilidade, mas NÃO SERÁ MAIS USADO
        na validação principal (apenas para relatórios ou análise)
        """
        # Horas já existentes (exceto a timesheet atual se estiver editando)
        existing_query = Task.objects.filter(
            timesheet__employee_id=employee_id,
            created_at=task_date
        )

        if exclude_timesheet_id:
            existing_query = existing_query.exclude(timesheet_id=exclude_timesheet_id)

        existing_hours = existing_query.aggregate(
            total=Sum('hour')
        )['total'] or Decimal('0.00')

        return existing_hours + new_hours

    @staticmethod
    def _validate_cross_timesheet_duplicate(
            employee_id: int,
            task_date: date,
            task_data: dict,
            exclude_timesheet_id: Optional[int]
    ):
        """
        ✅ REMOVIDO DA VALIDAÇÃO PRINCIPAL
        (agora coberto pela regra geral de não sobreposição)
        """
        # Esta função pode ser removida ou mantida apenas para logs
        pass

    @staticmethod
    def _validate_temporal_consistency(
            timesheet_date: date,
            task_date: date,
            employee_id: int
    ):
        """
        Valida consistência temporal entre datas
        """
        today = timezone.now().date()

        # 1. Tarefa não pode ser futura
        if task_date > today:
            raise field_error(
                "created_at",
                f"Tarefa não pode ser futura: {task_date} > {today}"
            )

        # 2. Timesheet não pode ser futura (já está no _validate_basic_data)

        # 3. Tarefa não pode ser posterior à timesheet
        if task_date > timesheet_date:
            raise field_error(
                "created_at",
                f"Tarefa ({task_date}) não pode ser posterior à timesheet ({timesheet_date})"
            )

    @staticmethod
    def _validate_retroactive_date(task_date: date):
        """
        Valida que tarefa não é muito antiga
        """
        today = timezone.now().date()
        days_diff = (today - task_date).days

        if days_diff > TimesheetValidator.MAX_RETROACTIVE_DAYS:
            raise field_error(
                "created_at",
                f"Tarefa muito antiga: {days_diff} dias atrás. "
                f"Máximo permitido: {TimesheetValidator.MAX_RETROACTIVE_DAYS} dias"
            )

    # ==================== MÉTODOS EXISTENTES (MANTIDOS) ====================

    @staticmethod
    def _validate_basic_data(data: dict, timesheet_id: Optional[int], employee_id: Optional[int]):
        """Validações básicas dos dados"""
        if not data.get("tasks"):
            raise field_error("tasks", "Timesheet deve conter pelo menos uma tarefa")

        if data.get("employee_id") is not None:
            employee = get_object_or_404(User, id=data["employee_id"])

            if data.get("department_id") is not None:
                department = get_object_or_404(Department, id=data["department_id"])
                if employee.department_id != department.id:
                    raise field_error("department_id", "Funcionário não pertence a este departamento")

        # Timesheet não pode ser futura
        if data.get("created_at") and data["created_at"] > timezone.now().date():
            raise field_error("created_at", "Não é possível criar timesheet para datas futuras")

    @staticmethod
    def _validate_task(task_data: dict, validation_level: str = "strict"):
        """Validação individual de cada tarefa"""
        task_hour = Decimal(str(task_data['hour']))

        # Horas devem ser positivas
        if task_hour <= Decimal('0.00'):
            raise field_error("hour", "Horas da tarefa devem ser maiores que zero")

        # Mínimo de 0.5h por tarefa
        if task_hour < TimesheetValidator.MIN_HOURS_PER_DAY:
            raise field_error(
                "hour",
                f"Tarefa muito curta: {task_hour}h. Mínimo: {TimesheetValidator.MIN_HOURS_PER_DAY}h"
            )

        # Máximo por tarefa
        if task_hour > TimesheetValidator.MAX_HOURS_PER_TASK:
            raise field_error(
                "hour",
                f"Tarefa não pode exceder {TimesheetValidator.MAX_HOURS_PER_TASK}h: {task_hour}h"
            )

        # Verificar se projeto e atividade existem
        get_object_or_404(Activity, id=task_data['activity_id'])
        get_object_or_404(Project, id=task_data['project_id'])

    @staticmethod
    def _validate_duplicate_timesheet(data: dict, timesheet_id: Optional[int], employee_id: Optional[int]):
        """Verifica se já existe uma timesheet do colaborador na mesma data"""
        emp_id = data.get('employee_id', employee_id)
        created_at = data.get('created_at')

        if not emp_id or not created_at:
            return

        duplicate_query = Timesheet.objects.filter(
            employee_id=emp_id,
            created_at=created_at
        )

        if timesheet_id:
            duplicate_query = duplicate_query.exclude(id=timesheet_id)

        if duplicate_query.exists():
            existing = duplicate_query.first()
            raise field_error(
                "created_at",
                f"Já existe uma timesheet (ID: {existing.id}) para este colaborador na data {created_at}. Status: {existing.status}"
            )

    @staticmethod
    def validate_timesheet_status(timesheet: Timesheet, allowed_statuses: list = ['rascunho']):
        if timesheet.status not in allowed_statuses:
            raise field_error("status", f"Timesheet com status '{timesheet.status}' não pode ser editada")

    @staticmethod
    def validate_user_permission(timesheet: Timesheet, user: User):
        if timesheet.employee_id != user.id and not user.is_staff:
            raise HttpError(403, "Você não tem permissão para editar esta timesheet")