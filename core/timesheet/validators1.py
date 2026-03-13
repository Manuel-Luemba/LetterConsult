from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Tuple, Dict, List
from django.utils import timezone
from ninja.errors import HttpError
from django.shortcuts import get_object_or_404

from core.erp.models import Department
from core.timesheet.models import Activity, Project, Timesheet
from core.user.models import User


def field_error(field: str, message: str):
    """Retorna erro estruturado por campo"""
    return HttpError(400, {field: [message]})


class TimesheetValidator:
    """Validador de timesheets com diferentes níveis de rigor"""

    # Constantes para configuração
    MAX_HOURS_PER_TASK = Decimal('16.00')
    MAX_HOURS_PER_DAY = Decimal('16.00')
    WARNING_HOURS_PER_TASK = Decimal('8.00')
    MIN_RECOMMENDED_HOURS_PER_DAY = Decimal('8.00')

    class ValidationConfig:
        """Configuração para diferentes cenários de validação"""
        STRICT = "strict"
        WARN_ONLY = "warn_only"

    @staticmethod
    def validate_timesheet_data(
            data: dict,
            timesheet_id: Optional[int] = None,
            employee_id: Optional[int] = None,
            validation_level: str = "strict",
            force_confirm: bool = False
    ) -> Tuple[bool, Dict[str, Decimal], List[str]]:
        """
        Valida todos os aspectos de uma timesheet

        Args:
            data: Dados da timesheet
            timesheet_id: ID da timesheet (para edição)
            employee_id: ID do funcionário
            validation_level: Nível de validação ("strict" ou "warn_only")
            force_confirm: Ignora warnings se True

        Returns:
            Tuple[is_valid, daily_totals, warnings]
        """
        daily_totals = defaultdict(Decimal)
        warnings = []

        try:
            # 1. Validações básicas obrigatórias
            TimesheetValidator._validate_basic_data(data, timesheet_id, employee_id)

            # 2. Validação de tarefas individuais e coleta de totais
            TimesheetValidator._validate_and_process_tasks(
                data,
                daily_totals,
                warnings,
                validation_level,
                force_confirm
            )

            # 3. Validação de totais diários
            if validation_level == TimesheetValidator.ValidationConfig.STRICT:
                TimesheetValidator._validate_daily_totals(daily_totals)

            # 4. Validação de recomendações (warnings)
            if not force_confirm:
                TimesheetValidator._add_recommendation_warnings(daily_totals, warnings)

            # 5. Validação de duplicidades com outras timesheets
            if validation_level == TimesheetValidator.ValidationConfig.STRICT:
                TimesheetValidator._validate_duplicate_timesheets(
                    data, timesheet_id, employee_id
                )

            return True, dict(daily_totals), warnings

        except HttpError:
            raise
        except Exception as e:
            raise HttpError(500, f"Erro na validação: {str(e)}")

    @staticmethod
    def _validate_basic_data(
            data: dict,
            timesheet_id: Optional[int],
            employee_id: Optional[int]
    ):
        """Validações básicas obrigatórias"""

        # Verifica se há tarefas
        if not data.get("tasks"):
            raise field_error("tasks", "Timesheet deve conter pelo menos uma tarefa")

        # Verifica relação funcionário-departamento
        TimesheetValidator._validate_employee_department(data)

        # Verifica data futura
        if data.get("created_at") and data["created_at"] > timezone.now().date():
            raise field_error("created_at", "Não é possível criar/editar timesheet para datas futuras")

    @staticmethod
    def _validate_employee_department(data: dict):
        """Valida se funcionário pertence ao departamento informado"""
        employee_id = data.get("employee_id")
        department_id = data.get("department_id")

        if employee_id is not None and department_id is not None:
            employee = get_object_or_404(User, id=employee_id)
            department = get_object_or_404(Department, id=department_id)

            if employee.department_id != department.id:
                raise field_error(
                    "department_id",
                    "Funcionário não pertence a este departamento"
                )

    @staticmethod
    def _validate_and_process_tasks(
            data: dict,
            daily_totals: defaultdict,
            warnings: list,
            validation_level: str,
            force_confirm: bool
    ):
        """Valida tarefas individuais e calcula totais diários"""
        task_combinations = set()

        for task_data in data.get('tasks', []):
            task_date = task_data['created_at']
            task_hour = Decimal(str(task_data['hour'])).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP
            )

            # Validação básica da tarefa
            TimesheetValidator._validate_single_task(task_data, validation_level)

            # Adiciona ao total diário
            daily_totals[task_date] += task_hour

            # Adiciona warning se tarefa exceder 8h (exceto com force_confirm)
            if (task_hour > TimesheetValidator.WARNING_HOURS_PER_TASK
                    and not force_confirm):
                warning_msg = (
                    f"Tarefa de {float(task_hour)}h excede 8 horas "
                    f"no dia {task_date}"
                )
                warnings.append(warning_msg)

            # Verifica duplicidade de combinação data/atividade/projeto
            TimesheetValidator._check_task_duplication(
                task_data, task_date, task_combinations
            )

    @staticmethod
    def _validate_single_task(task_data: dict, validation_level: str):
        """Valida uma única tarefa"""
        task_hour = Decimal(str(task_data['hour']))

        # Horas devem ser positivas
        if task_hour <= Decimal('0.00'):
            raise field_error("hour", "Horas da tarefa devem ser maiores que zero")

        # Limite máximo por tarefa
        if (validation_level == TimesheetValidator.ValidationConfig.STRICT
                and task_hour > TimesheetValidator.MAX_HOURS_PER_TASK):
            raise field_error(
                "hour",
                f"Tarefa não pode exceder {TimesheetValidator.MAX_HOURS_PER_TASK}h: {task_hour}h"
            )

        # Verifica se atividade e projeto existem
        get_object_or_404(Activity, id=task_data['activity_id'])
        get_object_or_404(Project, id=task_data['project_id'])

    @staticmethod
    def _check_task_duplication(
            task_data: dict,
            task_date: str,
            task_combinations: set
    ):
        """Verifica duplicidade de tarefas na mesma timesheet"""
        task_combination = (
            task_date,
            task_data['activity_id'],
            task_data['project_id']
        )

        if task_combination in task_combinations:
            activity = get_object_or_404(Activity, id=task_data['activity_id'])
            project = get_object_or_404(Project, id=task_data['project_id'])

            raise field_error(
                "tasks",
                f"Duplicidade: data {task_date}, "
                f"atividade '{activity.name}', "
                f"projeto '{project.name}'"
            )

        task_combinations.add(task_combination)

    @staticmethod
    def _validate_daily_totals(daily_totals: Dict[str, Decimal]):
        """Valida totais diários (apenas em modo strict)"""
        for task_date, total_hours in daily_totals.items():
            if total_hours > TimesheetValidator.MAX_HOURS_PER_DAY:
                raise field_error(
                    "tasks",
                    f"Total de horas no dia {task_date} é {float(total_hours)}h "
                    f"(máximo permitido: {TimesheetValidator.MAX_HOURS_PER_DAY}h)"
                )

    @staticmethod
    def _add_recommendation_warnings(
            daily_totals: Dict[str, Decimal],
            warnings: list
    ):
        """Adiciona warnings de recomendação"""
        for task_date, total_hours in daily_totals.items():
            if total_hours < TimesheetValidator.MIN_RECOMMENDED_HOURS_PER_DAY:
                warning_msg = (
                    f"Total de horas no dia {task_date} é {float(total_hours)}h "
                    f"(mínimo recomendado: {TimesheetValidator.MIN_RECOMMENDED_HOURS_PER_DAY}h)"
                )
                warnings.append(warning_msg)

    @staticmethod
    def _validate_duplicate_timesheets(
            data: dict,
            timesheet_id: Optional[int],
            employee_id: Optional[int]
    ):
        """Verifica se já existe timesheet para o mesmo funcionário na mesma data"""
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
                f"Já existe uma timesheet (ID: {existing.id}) para este colaborador "
                f"na data {created_at}. Status: {existing.status}"
            )

    @staticmethod
    def validate_timesheet_status(
            timesheet: Timesheet,
            allowed_statuses: list = ['rascunho']
    ):
        """Valida se a timesheet está em status editável"""
        if timesheet.status not in allowed_statuses:
            raise field_error(
                "status",
                f"Timesheet com status '{timesheet.status}' não pode ser editada"
            )

    @staticmethod
    def validate_user_permission(timesheet: Timesheet, user: User):
        """
        Valida se usuário tem permissão para editar a timesheet

        Permite:
        1. Dono da timesheet
        2. Usuários staff
        3. Gestores do mesmo departamento
        """
        # Verificação direta: dono ou staff
        if timesheet.employee_id == user.id or getattr(user, 'is_staff', False):
            return

        # Verificação para gestores do mesmo departamento
        if user.groups.filter(name='gestores').exists():
            user_department = getattr(user, 'department', None)
            employee_department = getattr(timesheet.employee, 'department', None)

            if user_department and employee_department and user_department == employee_department:
                return

        raise HttpError(
            403,
            "Você não tem permissão para editar esta timesheet. "
            "Apenas o proprietário, administradores ou gestores do mesmo departamento podem acessar."
        )