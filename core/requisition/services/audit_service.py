import logging
from ..models import RequisitionAuditLog

logger = logging.getLogger(__name__)

class AuditService:
    @staticmethod
    def log_change(purchase_request, user, action_type, description, previous_values=None, new_values=None):
        """
        Gera um registo de auditoria para uma alteração relevante na requisição.
        Protegido contra falhas para não bloquear o fluxo principal de dados.
        """
        try:
            log = RequisitionAuditLog.objects.create(
                purchase_request=purchase_request,
                performed_by=user,
                action_type=action_type,
                action_description=description,
                previous_values=previous_values,
                new_values=new_values
            )
            logger.info(f"Audit log criado: {action_type} na requisição {purchase_request.id} por {user.username}")
            return log
        except Exception as e:
            logger.error(f"Erro ao criar registo de auditoria: {str(e)}")
            return None
