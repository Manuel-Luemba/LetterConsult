# core/timesheet/services/timesheet_workflow_service.py
import logging
from django.db import transaction
from django.utils import timezone
from ninja.errors import HttpError

from core.timesheet.models import Timesheet, TimesheetStatusChange, Task
from .timesheet_notification_service import TimesheetNotificationService
from ..validators import TimesheetValidator

logger = logging.getLogger(__name__)

class TimesheetWorkflowService:
    """
    Serviço responsável por gerir todo o fluxo de aprovações de Timesheets.
    """

    def __init__(self, timesheet: Timesheet):
        self.timesheet = timesheet
        self.notifications = TimesheetNotificationService()

    @transaction.atomic
    def submit_for_approval(self, submitted_by):
        """
        Submete a timesheet para aprovação do coordenador.
        """
        logger.info(f"Submetendo timesheet {self.timesheet.id} para aprovação.")

        # 1. Validação básica (garantir que tem tarefas e horas são válidas)
        if self.timesheet.tasks.count() == 0:
            raise HttpError(400, "Nã é possível submeter uma timesheet sem tarefas.")

        # 2. Atualizar estado
        old_status = self.timesheet.status
        self.timesheet.status = 'submetido'
        self.timesheet.submitted_at = timezone.now().date()
        self.timesheet.submitted_by = submitted_by
        self.timesheet.save()

        # 3. Registar histórico
        TimesheetStatusChange.objects.create(
            timesheet=self.timesheet,
            old_status=old_status,
            new_status='submetido',
            changed_by=submitted_by,
            notes="Timesheet submetida para aprovação."
        )

        # 4. Notificar coordenador do departamento
        self.notifications.notify_approvers(self.timesheet)

        return self.timesheet

    @transaction.atomic
    def approve(self, approver, comments="", task_reviews=None):
        """
        Aprova a timesheet (total ou parcial por tarefas).
        """
        logger.info(f"Aprovando timesheet {self.timesheet.id} por {approver.username}.")

        # 1. Validar permissão (deve ser coordenador ou admin)
        # O User.is_approver já faz essa checagem de grupo/departamento
        if not approver.is_approver:
            raise HttpError(403, "Sem permissão para aprovar timesheets.")

        old_status = self.timesheet.status

        # 2. Processar revisões de tarefas individuais (se houver)
        if task_reviews:
            for review in task_reviews:
                task = Task.objects.filter(id=review.task_id, timesheet=self.timesheet).first()
                if task:
                    task.status = review.status
                    task.review_comment = review.review_comment
                    task.save()

        # 3. Determinar novo estado global
        # Se alguma tarefa foi rejeitada ou precisa de melhoria, o estado muda.
        # Caso contrário, aprovado total.
        has_rejected = self.timesheet.tasks.filter(status='rejected').exists()
        has_suggestions = self.timesheet.tasks.filter(status='needs_improvement').exists()

        if has_rejected:
            new_status = 'com_rejeitadas'
        elif has_suggestions:
            new_status = 'com_sugestoes'
        else:
            new_status = 'aprovado'
            # Marcar todas as tarefas como aprovadas se não houver rejeitadas/sugestões
            self.timesheet.tasks.filter(status='pending').update(status='approved')

        self.timesheet.status = new_status
        self.timesheet.save()

        # 4. Registar histórico
        TimesheetStatusChange.objects.create(
            timesheet=self.timesheet,
            old_status=old_status,
            new_status=new_status,
            changed_by=approver,
            notes=comments or f"Aprovação processada: {new_status}"
        )

        # 5. Notificar colaborador
        self.notifications.notify_requestor(self.timesheet, approver, "aprovada" if new_status == 'aprovado' else "revisada com observações")

        return self.timesheet

    @transaction.atomic
    def reject(self, approver, reason):
        """
        Rejeita totalmente a timesheet.
        """
        if not reason:
            raise HttpError(400, "Motivo é obrigatório para rejeição.")

        old_status = self.timesheet.status
        self.timesheet.status = 'com_rejeitadas'
        self.timesheet.save()

        # Marcar todas as tarefas pendentes como rejeitadas
        self.timesheet.tasks.filter(status='pending').update(status='rejected', review_comment=reason)

        TimesheetStatusChange.objects.create(
            timesheet=self.timesheet,
            old_status=old_status,
            new_status='com_rejeitadas',
            changed_by=approver,
            notes=reason
        )

        self.notifications.notify_requestor(self.timesheet, approver, "rejeitada", reason)

        return self.timesheet

    @transaction.atomic
    def request_changes(self, approver, comments):
        """
        Solicita melhorias na timesheet.
        """
        old_status = self.timesheet.status
        self.timesheet.status = 'com_sugestoes'
        self.timesheet.save()

        TimesheetStatusChange.objects.create(
            timesheet=self.timesheet,
            old_status=old_status,
            new_status='com_sugestoes',
            changed_by=approver,
            notes=comments
        )

        self.notifications.notify_requestor(self.timesheet, approver, "solicitada melhoria", comments)

        return self.timesheet
