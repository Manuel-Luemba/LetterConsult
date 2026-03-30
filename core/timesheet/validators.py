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
    # CONSTANTES DE VALIDAÃ‡ÃƒO
    MAX_HOURS_PER_TASK = Decimal('16.00')  # MÃ¡ximo por tarefa individual
    MAX_HOURS_PER_DAY = Decimal('16.00')  # MÃ¡ximo por dia por colaborador (APENAS NA MESMA TIMESHEET)
    MAX_RETROACTIVE_DAYS = 30  # MÃ¡ximo de dias para registrar tarefas passadas
    MIN_HOURS_PER_DAY = Decimal('0.00')  # MÃ­nimo por tarefa

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
        "Entre duas timesheets diferentes nÃ£o pode haver tarefas com as mesmas datas"
        """
        daily_totals = defaultdict(Decimal)
        daily_warnings = defaultdict(list)
        all_warnings = []

        validation_level = data.get("validation_level", "strict")
        force_confirm = data.get("force_confirm", False)

        # ðŸš€ OtimizaÃ§Ã£o N+1 Queries: Carregar Projetos e Atividades em lote
        task_list = data.get('tasks', [])
        project_ids = {t['project_id'] for t in task_list if 'project_id' in t}
        activity_ids = {t['activity_id'] for t in task_list if 'activity_id' in t}

        projects_dict = {p.id: p.name for p in Project.objects.filter(id__in=project_ids)}
        activities_dict = {a.id: a.name for a in Activity.objects.filter(id__in=activity_ids)}

        existing_projects = set(projects_dict.keys())
        existing_activities = set(activities_dict.keys())

        try:
            # 1. VALIDAÃ‡Ã•ES BÃSICAS (sempre obrigatÃ³rias)
            TimesheetValidator._validate_basic_data(data, timesheet_id, employee_id)

            # Obter dados importantes
            timesheet_date = data.get('created_at')
            emp_id = data.get('employee_id', employee_id)

            # 2. âœ… NOVA REGRA: VALIDAR SOBREPOSIÃ‡ÃƒO DE DATAS ENTRE TIMESHEETS
            if emp_id:
                task_dates = [task['created_at'] for task in data.get('tasks', [])]
                TimesheetValidator._validate_no_date_overlap(
                    employee_id=emp_id,
                    task_dates=task_dates,
                    exclude_timesheet_id=timesheet_id,
                    context="criaÃ§Ã£o" if not timesheet_id else "atualizaÃ§Ã£o"
                )

            # 3. VALIDAÃ‡ÃƒO POR TAREFA (dentro da mesma timesheet)
            task_combinations = set()

            for task_data in data.get('tasks', []):
                task_date = task_data['created_at']
                task_hour = Decimal(str(task_data['hour']))

                # Acumular para total diÃ¡rio (APENAS nesta timesheet)
                daily_totals[task_date] += task_hour

                # ValidaÃ§Ã£o individual da tarefa (com cache de IDs)
                TimesheetValidator._validate_task(task_data, existing_projects, existing_activities, validation_level)

                # ValidaÃ§Ã£o temporal
                if timesheet_date:
                    TimesheetValidator._validate_temporal_consistency(
                        timesheet_date, task_date, emp_id
                    )

                # ValidaÃ§Ã£o retroativa
                TimesheetValidator._validate_retroactive_date(task_date)

                # âœ… REMOVIDO: ValidaÃ§Ã£o de duplicidade ENTRE timesheets
                # (agora coberta pela regra geral de nÃ£o sobreposiÃ§Ã£o)

                # ValidaÃ§Ã£o de duplicidade DENTRO da timesheet
                task_combination = (
                    task_date,
                    task_data['project_id'],
                    task_data['activity_id']
                )

                if task_combination in task_combinations:
                    activity_name = activities_dict.get(task_data['activity_id'], 'Desconhecida')
                    project_name = projects_dict.get(task_data['project_id'], 'Desconhecido')
                    raise field_error(
                        "tasks",
                        f"Tarefa duplicada: dia {task_date}, projeto '{project_name}', atividade '{activity_name}'"
                    )
                task_combinations.add(task_combination)

                # âš ï¸ Warning para tarefa longa (apenas se nÃ£o for force_confirm)
                if not force_confirm and task_hour > Decimal('8.00'):
                    warning_msg = f"Tarefa de {task_hour}h excede 8 horas no dia {task_date}"
                    daily_warnings[task_date].append(warning_msg)

            # 4. âœ… VALIDAÃ‡ÃƒO SIMPLIFICADA: Total diÃ¡rio APENAS nesta timesheet
            # NÃƒO precisa mais validar entre timesheets diferentes!
            for task_date, total_in_this_timesheet in daily_totals.items():
                # Validar limite mÃ¡ximo diÃ¡rio (APENAS nesta timesheet)
                if total_in_this_timesheet > TimesheetValidator.MAX_HOURS_PER_DAY:
                    raise field_error(
                        "tasks",
                        f"Total diÃ¡rio em {task_date} Ã© {float(total_in_this_timesheet)}h "
                        f"(mÃ¡ximo permitido: {TimesheetValidator.MAX_HOURS_PER_DAY}h)"
                    )

                # AVISOS OPCIONAIS (apenas se nÃ£o for force_confirm)
                if not force_confirm:
                    if total_in_this_timesheet > Decimal('8.00'):
                        warning_msg = (
                            f"âš ï¸ Total de horas no dia {task_date} Ã© {float(total_in_this_timesheet)}h "
                            f"(superior Ã s 8h normais). Deseja confirmar?"
                        )
                        daily_warnings[task_date].append(warning_msg)
                    elif total_in_this_timesheet < Decimal('8.00'):
                        warning_msg = (
                            f"âš ï¸ Total de horas no dia {task_date} Ã© {float(total_in_this_timesheet)}h "
                            f"(mÃ­nimo recomendado: 8h). Deseja confirmar?"
                        )
                        daily_warnings[task_date].append(warning_msg)

            # 5. ValidaÃ§Ã£o de duplicidade de timesheet na mesma data
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
            raise HttpError(500, f"Erro na validaÃ§Ã£o: {str(e)}")

    # ==================== NOVA FUNÃ‡ÃƒO PRINCIPAL ====================

    @staticmethod
    def _validate_no_date_overlap(
            employee_id: int,
            task_dates: List[date],
            exclude_timesheet_id: Optional[int] = None,
            context: str = "criaÃ§Ã£o"
    ) -> None:
        """
        REGRA SIMPLES E CLARA
        """
        if not task_dates:
            return

        # Buscar datas jÃ¡ ocupadas
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
                f"A data {dates_list[0]} jÃ¡ estÃ¡ ocupada em outra timesheet. "
                f"Escolha uma data diferente."
            )
        else:
            dates_str = ", ".join(dates_list)
            raise field_error(
                "tasks",
                f"As datas {dates_str} jÃ¡ estÃ£o ocupadas em outras timesheets. "
                f"Escolha datas diferentes."
            )
    # ==================== MÃ‰TODOS AUXILIARES (SIMPLIFICADOS) ====================

    @staticmethod
    def _validate_temporal_consistency(
            timesheet_date: date,
            task_date: date,
            employee_id: int
    ):
        """
        Valida consistÃªncia temporal entre datas
        """
        today = timezone.now().date()

        # 1. Tarefa nÃ£o pode ser futura
        if task_date > today:
            raise field_error(
                "created_at",
                f"Tarefa nÃ£o pode ser futura: {task_date} > {today}"
            )

        # 2. Timesheet nÃ£o pode ser futura (jÃ¡ estÃ¡ no _validate_basic_data)

        # 3. Tarefa nÃ£o pode ser posterior Ã  timesheet
        if task_date > timesheet_date:
            raise field_error(
                "created_at",
                f"Tarefa ({task_date}) nÃ£o pode ser posterior Ã  timesheet ({timesheet_date})"
            )

    @staticmethod
    def _validate_retroactive_date(task_date: date):
        """
        Valida que tarefa nÃ£o Ã© muito antiga
        """
        today = timezone.now().date()
        days_diff = (today - task_date).days

        if days_diff > TimesheetValidator.MAX_RETROACTIVE_DAYS:
            raise field_error(
                "created_at",
                f"Tarefa muito antiga: {days_diff} dias atrÃ¡s. "
                f"MÃ¡ximo permitido: {TimesheetValidator.MAX_RETROACTIVE_DAYS} dias"
            )

    # ==================== MÃ‰TODOS EXISTENTES (MANTIDOS) ====================

    @staticmethod
    def _validate_basic_data(data: dict, timesheet_id: Optional[int], employee_id: Optional[int]):
        """ValidaÃ§Ãµes bÃ¡sicas dos dados"""
        if not data.get("tasks"):
            raise field_error("tasks", "Timesheet deve conter pelo menos uma tarefa")

        if data.get("employee_id") is not None:
            employee = get_object_or_404(User, id=data["employee_id"])

            if data.get("department_id") is not None:
                department = get_object_or_404(Department, id=data["department_id"])
                if employee.department_id != department.id:
                    raise field_error("department_id", "FuncionÃ¡rio nÃ£o pertence a este departamento")

        # Timesheet nÃ£o pode ser futura
        if data.get("created_at") and data["created_at"] > timezone.now().date():
            raise field_error("created_at", "NÃ£o Ã© possÃ­vel criar timesheet para datas futuras")

    @staticmethod
    def _validate_task(task_data: dict, existing_projects: set, existing_activities: set, validation_level: str = "strict"):
        """ValidaÃ§Ã£o individual de cada tarefa"""
        task_hour = Decimal(str(task_data['hour']))

        # Horas devem ser positivas
        if task_hour <= Decimal('0.00'):
            raise field_error("hour", "Horas da tarefa devem ser maiores que zero")

        # MÃ­nimo de 0.5h por tarefa
        if task_hour < TimesheetValidator.MIN_HOURS_PER_DAY:
            raise field_error(
                "hour",
                f"Tarefa muito curta: {task_hour}h. MÃ­nimo: {TimesheetValidator.MIN_HOURS_PER_DAY}h"
            )

        # MÃ¡ximo por tarefa
        if task_hour > TimesheetValidator.MAX_HOURS_PER_TASK:
            raise field_error(
                "hour",
                f"Tarefa nÃ£o pode exceder {TimesheetValidator.MAX_HOURS_PER_TASK}h: {task_hour}h"
            )

        # Verificar se projeto e atividade existem (via cache)
        if task_data['activity_id'] not in existing_activities:
            raise field_error("activity_id", f"Atividade (ID: {task_data['activity_id']}) nÃ£o encontrada")
        if task_data['project_id'] not in existing_projects:
            raise field_error("project_id", f"Projeto (ID: {task_data['project_id']}) nÃ£o encontrado")

    @staticmethod
    def _validate_duplicate_timesheet(data: dict, timesheet_id: Optional[int], employee_id: Optional[int]):
        """Verifica se jÃ¡ existe uma timesheet do colaborador na mesma data"""
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
                f"JÃ¡ existe uma timesheet (ID: {existing.id}) para este colaborador na data {created_at}. Status: {existing.status}"
            )

    @staticmethod
    def validate_timesheet_status(timesheet: Timesheet, allowed_statuses: list = ['rascunho', 'com_sugestoes', 'com_rejeitadas']):
        if timesheet.status not in allowed_statuses:
            raise field_error("status", f"Timesheet com status '{timesheet.status}' nÃ£o pode ser editada")

    @staticmethod
    def validate_user_permission(timesheet: Timesheet, user: User):
        if timesheet.employee_id != user.id and not user.is_staff:
            raise HttpError(403, "VocÃª nÃ£o tem permissÃ£o para editar esta timesheet")
