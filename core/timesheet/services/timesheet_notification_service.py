# core/timesheet/services/timesheet_notification_service.py
import logging
import threading
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from django.utils.html import strip_tags
from django.utils import timezone
from django.db import IntegrityError
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from core.erp.models import Notification
from core.user.models import User

logger = logging.getLogger(__name__)

class TimesheetNotificationService:
    """
    Serviço centralizado de notificações para o módulo de Timesheet.
    """

    def __init__(self):
        self.from_email = settings.DEFAULT_FROM_EMAIL
        self.site_url = getattr(settings, 'SITE_URL', 'http://localhost:5173')

    def notify_approvers(self, timesheet):
        """
        Evento: TS_SUBMITTED
        Notifica coordenadores do departamento sobre a submissão.
        """
        department = timesheet.department
        if not department:
            logger.warning(f"Timesheet {timesheet.id} sem departamento.")
            return

        approvers = [u for u in User.objects.filter(department=department) if u.is_approver]
        
        event_type = 'TS_SUBMITTED'
        action_url = f'/timesheets/{timesheet.id}'
        message = f'Timesheet #{timesheet.id} de {timesheet.employee.get_full_name()} aguarda aprovação.'

        for approver in approvers:
            if approver == timesheet.employee:
                continue # Não notificar a si mesmo se for coordenador

            self._create_notification(approver, message, event_type, timesheet, action_url)
            
            # Email (OPCIONAL: Podes desativar ou usar um template específico)
            self._send_email_safe(
                user=approver,
                subject=f'Timesheet #{timesheet.id} Pendente de Aprovação',
                template='emails/timesheet_pending.html',
                context={
                    'timesheet': timesheet,
                    'approver': approver,
                    'action_url': f'{self.site_url}{action_url}',
                }
            )

    def notify_requestor(self, timesheet, actor, action_label, reason=""):
        """
        Evento: TS_ACTION_TAKEN
        Notifica o colaborador sobre o resultado da aprovação/rejeição.
        """
        event_type = 'TS_ACTION_TAKEN'
        action_url = f'/timesheets/{timesheet.id}'
        message = f'Sua timesheet #{timesheet.id} foi {action_label} por {actor.get_full_name()}.'
        if reason:
            message += f' Motivo: {reason}'

        self._create_notification(timesheet.employee, message, event_type, timesheet, action_url)
        
        self._send_email_safe(
            user=timesheet.employee,
            subject=f'Feedback sobre a sua Timesheet #{timesheet.id}',
            template='emails/timesheet_feedback.html',
            context={
                'timesheet': timesheet,
                'actor': actor,
                'action_label': action_label,
                'reason': reason,
                'action_url': f'{self.site_url}{action_url}',
            }
        )

    # ============================================
    # MÉTODOS PRIVADOS (Padrão Unificado)
    # ============================================

    def _create_notification(self, user, message, event_type, timesheet, action_url=''):
        """
        Cria notificação In-App e envia WebSocket.
        """
        ts_id = timesheet.id if timesheet else None
        notification_key = f'TS-{ts_id}|{event_type}|user_{user.id}'

        try:
            Notification.objects.create(
                user=user,
                message=message,
                event_type=event_type,
                notification_key=notification_key,
                timesheet_id=ts_id,
                action_url=action_url,
                created_at=timezone.now(),
            )
            
            # BroadCast Realtime
            self._broadcast_realtime(user, 'timesheet.status_changed', {
                'id': ts_id,
                'status': timesheet.status if timesheet else 'N/A',
                'message': message
            })
        except IntegrityError:
            pass # Ignora duplicados
        except Exception as e:
            logger.error(f'Erro ao criar notificação TS: {e}')

    def _send_email_safe(self, user, subject, template, context):
        if not user.email: return

        try:
            context['site_url'] = self.site_url
            context['contacts'] = getattr(settings, 'ENGCONSULT_CONTACTS', {})
            
            # Tentar renderizar. Se falhar template, apenas loga (não trava o workflow)
            try:
                html_message = render_to_string(template, context)
                plain_message = strip_tags(html_message)
            except Exception as e:
                logger.debug(f'Template {template} não encontrado ou erro na renderização: {e}')
                return

            def _send():
                try:
                    send_mail(subject, plain_message, self.from_email, [user.email], html_message=html_message)
                except Exception as e:
                    logger.error(f'Falha envio email TS: {e}')

            threading.Thread(target=_send, daemon=True).start()
        except Exception:
            pass

    def _broadcast_realtime(self, user, event_type, payload):
        try:
            channel_layer = get_channel_layer()
            group_name = f"user_{user.id}"
            async_to_sync(channel_layer.group_send)(
                group_name,
                {
                    'type': 'timesheet_event',
                    'data': {
                        'type': event_type,
                        'payload': payload,
                        'timestamp': timezone.now().isoformat()
                    }
                }
            )
        except Exception:
            pass
