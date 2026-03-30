import logging
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from django.db import transaction

# Absolute Imports baseados na estrutura do projeto
from core.requisition.models import PurchaseRequest, Approval
from core.user.models import User
from core.requisition.services.notification_service import NotificationService
from core.requisition.services.PurchasingAnalysisService import PurchasingAnalysisService
from core.requisition.services.workflow_service import WorkflowService
from core.requisition.services.audit_service import AuditService

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Auto-approves Purchase Requests that have been in AWAITING_REQUESTER_DECISION for more than 48 hours.'

    def handle(self, *args, **options):
        # 1. Filtro: RCs em Espera há mais de 48h
        limit_date = timezone.now() - timedelta(hours=48)
        queryset = PurchaseRequest.objects.filter(
            status='AWAITING_REQUESTER_DECISION',
            awaiting_decision_since__isnull=False,
            awaiting_decision_since__lte=limit_date
        )

        self.stdout.write(f"A examinar {queryset.count()} requisições para timeout...")
        count = 0
        
        # Obter um utilizador administrador para registar a ação automática de auditoria
        system_user = User.objects.filter(is_superuser=True).first()
        if not system_user:
            self.stdout.write(self.style.ERROR("Nenhum utilizador administrador encontrado para registar o timeout automático."))
            return

        for pr in queryset:
            try:
                with transaction.atomic():
                    # 1. Trancar itens REJECTED (Aceitação Parcial Forçada)
                    items_list = list(pr.items.all())
                    for item in items_list:
                        if item.status == 'REJECTED':
                            item.is_locked = True
                            item.save()

                    # 2. Recalcular Total e Poupança (Excluindo rejeitados)
                    total = sum([itm.total_price or 0 for itm in items_list if itm.status != 'REJECTED'])
                    old_total = pr.total_amount
                    pr.total_amount = total
                    pr.approved_total = total
                    pr.savings_amount = old_total - total

                    # 3. Decidir destino (Aprovação ou Direção) baseado na alçada
                    analysis = PurchasingAnalysisService(pr)
                    limit = getattr(analysis, 'company_limit', 5000000.00)
                    workflow = WorkflowService(pr)

                    if total > limit:
                        # Acima do limite -> Forward para Direção
                        workflow.forward_to_director(system_user, 'Timeout 48h: Encaminhado automaticamente devido a limite de alçada.')
                    else:
                        # Dentro do limite -> Aprovar Parcial
                        pr.status = 'PARTIALLY_APPROVED'
                        pr.save()
                        
                        # Atualizar workflow
                        if hasattr(pr, 'workflow') and pr.workflow:
                            pr.workflow.current_step = 'APPROVED'
                            pr.workflow.completed_at = timezone.now()
                            pr.workflow.save()

                    # 4. Audit Log de Timeout
                    AuditService.log_change(
                        purchase_request=pr,
                        user=system_user,
                        action_type='REVIEW_PARCIAL',
                        description='[SISTEMA]: Auto-aprovação Parcial efetuada por timeout de 48h (Sem resposta do solicitante).',
                        previous_values={"status_anterior": "AWAITING_REQUESTER_DECISION"},
                        new_values={"status_novo": pr.status}
                    )

                    # 5. Notificar via WebSocket
                    try:
                        NotificationService().notify_item_updated(pr, system_user)
                    except Exception:
                        pass # WebSocket falha silenciosamente se desconectado
                        
                    count += 1
                    logger.info(f"RC #{pr.id} processada por timeout (48h). Novo status: {pr.status}")

            except Exception as e:
                logger.error(f"Erro ao processar timeout da RC #{pr.id}: {str(e)}")

        self.stdout.write(self.style.SUCCESS(f"Sucesso: {count} RCs auto-processadas por timeout (48h)."))
