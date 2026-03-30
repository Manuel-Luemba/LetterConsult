# services/notification_service.py
"""
NotificationService — Event-driven notification system.

Cada evento do workflow gera notificações (in-app + email) para os utilizadores relevantes.
Utiliza deduplicação via notification_key para evitar duplicados.
"""
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from django.utils.html import strip_tags
from django.utils import timezone
from django.db.models import Q
from django.db import IntegrityError
import logging
import threading
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from core.erp.models import Notification
from core.user.models import User

logger = logging.getLogger(__name__)


class NotificationService:
    """
    Serviço centralizado de notificações.
    Cada método público corresponde a um evento do workflow.
    """

    def __init__(self):
        self.from_email = settings.DEFAULT_FROM_EMAIL
        self.site_url = getattr(settings, 'SITE_URL', 'http://localhost:8000')

    # ============================================
    # EVENTOS PÚBLICOS (chamados pelo WorkflowService)
    # ============================================

    def notify_approvers(self, purchase_request, approvers, step):
        """
        Evento: RQ_SUBMITTED
        Notifica aprovadores que têm uma requisição pendente.
        """
        event_type = 'RQ_SUBMITTED'
        action_url = f'/requisitions/{purchase_request.id}'

        for approver in approvers:
            message = f'Requisição #{purchase_request.code} aguarda a sua aprovação ({step})'

            self._create_notification(
                user=approver,
                message=message,
                event_type=event_type,
                purchase_request=purchase_request,
                action_url=action_url,
            )

            self._send_email_safe(
                user=approver,
                subject=f'Requisição #{purchase_request.code} Pendente de Aprovação',
                template='emails/pending_approval.html',
                context={
                    'request': purchase_request,
                    'approver': approver,
                    'step': step,
                    'approval_url': f'{self.site_url}{action_url}',
                }
            )

    def notify_purchasing_central(self, purchase_request):
        """
        Evento: RQ_SENT_PURCHASING
        Notifica Central de Compras sobre nova requisição para análise.
        """
        from django.contrib.auth.models import Group

        purchasing_group = Group.objects.filter(
            Q(name__iexact='PurchasingCentral') |
            Q(name__icontains='compras') |
            Q(name__icontains='purchasing')
        ).first()

        if not purchasing_group:
            logger.warning("Grupo 'PurchasingCentral' não encontrado. Nenhuma notificação enviada.")
            return

        purchasing_users = purchasing_group.user_set.filter(is_active=True)
        event_type = 'RQ_SENT_PURCHASING'
        action_url = f'/requisitions/{purchase_request.id}'

        for user in purchasing_users:
            message = f'Nova requisição #{purchase_request.code} para análise'

            self._create_notification(
                user=user,
                message=message,
                event_type=event_type,
                purchase_request=purchase_request,
                action_url=action_url,
            )

            self._send_email_safe(
                user=user,
                subject=f'Nova Requisição #{purchase_request.code} para Análise',
                template='emails/new_for_purchasing.html',
                context={
                    'request': purchase_request,
                    'user': user,
                    'analysis_url': f'{self.site_url}{action_url}',
                }
            )

        # Também notificar o autor que a RQ avançou
        self._create_notification(
            user=purchase_request.requested_by,
            message=f'Sua requisição #{purchase_request.code} foi aprovada e enviada para a Central de Compras',
            event_type=event_type,
            purchase_request=purchase_request,
            action_url=action_url,
        )

    def notify_directors(self, purchase_request, reason):
        """
        Evento: RQ_FORWARDED_DIRECTOR
        Notifica diretores sobre requisição encaminhada pela Central.
        """
        from django.contrib.auth.models import Group

        director_groups = Group.objects.filter(
            Q(name__iexact='Director') |
            Q(name__iexact='DeputyDirector') |
            Q(name__icontains='diretor') |
            Q(name__icontains='director')
        )
        directors = User.objects.filter(groups__in=director_groups, is_active=True).distinct()

        if not directors.exists():
            logger.warning("Nenhum diretor encontrado para notificações.")
            return

        event_type = 'RQ_FORWARDED_DIRECTOR'
        action_url = f'/requisitions/{purchase_request.id}'

        for director in directors:
            message = f'Requisição #{purchase_request.code} aguarda aprovação da Direção'

            self._create_notification(
                user=director,
                message=message,
                event_type=event_type,
                purchase_request=purchase_request,
                action_url=action_url,
            )

            self._send_email_safe(
                user=director,
                subject=f'Requisição #{purchase_request.code} Aguarda Aprovação da Direção',
                template='emails/director_approval.html',
                context={
                    'request': purchase_request,
                    'director': director,
                    'reason': reason,
                    'approval_url': f'{self.site_url}{action_url}',
                }
            )

        # Notificar autor
        self._create_notification(
            user=purchase_request.requested_by,
            message=f'Sua requisição #{purchase_request.code} foi encaminhada para a Direção',
            event_type=event_type,
            purchase_request=purchase_request,
            action_url=action_url,
        )

    def notify_requestor_approved(self, purchase_request):
        """
        Evento: RQ_APPROVED_FINAL
        Notifica solicitante que a requisição teve aprovação final.
        """
        event_type = 'RQ_APPROVED_FINAL'
        action_url = f'/requisitions/{purchase_request.id}'
        message = f'Sua requisição #{purchase_request.code} foi aprovada! ✅'

        self._create_notification(
            user=purchase_request.requested_by,
            message=message,
            event_type=event_type,
            purchase_request=purchase_request,
            action_url=action_url,
        )

        self._send_email_safe(
            user=purchase_request.requested_by,
            subject=f'Requisição #{purchase_request.code} Aprovada',
            template='emails/request_approved.html',
            context={
                'request': purchase_request,
                'requestor': purchase_request.requested_by,
                'status': 'aprovada',
            }
        )

    def notify_requestor_rejected(self, purchase_request, approver, reason):
        """
        Evento: RQ_REJECTED_DEPT / RQ_REJECTED_PURCHASING / RQ_REJECTED_DIRECTOR
        Notifica solicitante que a requisição foi rejeitada.
        """
        event_type = 'RQ_REJECTED_DEPT'
        action_url = f'/requisitions/{purchase_request.id}'
        message = f'Sua requisição #{purchase_request.code} foi rejeitada por {approver.get_full_name()}. Motivo: {reason}'

        self._create_notification(
            user=purchase_request.requested_by,
            message=message,
            event_type=event_type,
            purchase_request=purchase_request,
            action_url=action_url,
        )

        self._send_email_safe(
            user=purchase_request.requested_by,
            subject=f'Requisição #{purchase_request.code} Rejeitada',
            template='emails/request_rejected.html',
            context={
                'request': purchase_request,
                'approver': approver,
                'reason': reason,
                'requestor': purchase_request.requested_by,
                'status': 'rejeitada',
            }
        )

    def notify_purchasing_edit(self, purchase_request, editor):
        """
        Evento: RQ_PURCHASING_EDITED
        Notifica solicitante que a Central editou a requisição.
        """
        event_type = 'RQ_PURCHASING_EDITED'
        action_url = f'/requisitions/{purchase_request.id}'
        message = f'Sua requisição #{purchase_request.code} foi editada pela Central de Compras'

        self._create_notification(
            user=purchase_request.requested_by,
            message=message,
            event_type=event_type,
            purchase_request=purchase_request,
            action_url=action_url,
        )

        self._send_email_safe(
            user=purchase_request.requested_by,
            subject=f'Requisição #{purchase_request.code} Editada pela Central',
            template='emails/purchasing_edited.html',
            context={
                'request': purchase_request,
                'editor': editor,
                'requestor': purchase_request.requested_by,
            }
        )

    def notify_group_approval(self, purchase_request, group_names, approver):
        """
        Evento: RQ_APPROVED_DEPT
        Notifica outros membros do grupo que a requisição já foi aprovada por alguém.
        """
        event_type = 'RQ_APPROVED_DEPT'
        action_url = f'/requisitions/{purchase_request.id}'

        users = User.objects.filter(groups__name__in=group_names, is_active=True).distinct()

        for user in users:
            if user == approver:
                continue  # Não notificar quem aprovou

            message = f'Requisição #{purchase_request.code} aprovada por {approver.get_full_name()}'

            self._create_notification(
                user=user,
                message=message,
                event_type=event_type,
                purchase_request=purchase_request,
                action_url=action_url,
            )

            self._send_email_safe(
                user=user,
                subject=f'Requisição #{purchase_request.code} aprovada por {approver.get_full_name()}',
                template='emails/other_approver_notified.html',
                context={
                    'request': purchase_request,
                    'approver': approver,
                    'user': user,
                }
            )

    def notify_batch(self, purchase_requests, action, actor, comments="", reason=None):
        """
        Processa notificações em lote.
        """
        for pr in purchase_requests:
            try:
                if action == 'approve':
                    self.notify_requestor_approved(pr)
                elif action == 'forward_to_director':
                    self.notify_directors(pr, comments or 'Encaminhado em lote')
                elif action == 'reject':
                    self.notify_requestor_rejected(pr, actor, reason or '')
            except Exception:
                logger.exception(f'Batch notification failed for request {getattr(pr, "id", "?")}')

    # ============================================
    # MÉTODOS PRIVADOS
    # ============================================

    def _create_notification(self, user, message, event_type, purchase_request, action_url=''):
        """
        Cria notificação in-app com deduplicação via notification_key.
        Se já existir uma notificação com a mesma key, não cria duplicado.
        """
        pr_id = purchase_request.id if purchase_request else None
        notification_key = f'RQ-{pr_id}|{event_type}|user_{user.id}'

        try:
            Notification.objects.create(
                user=user,
                message=message,
                event_type=event_type,
                notification_key=notification_key,
                purchase_request_id=pr_id,
                action_url=action_url,
                created_at=timezone.now(),
            )
            logger.info(f'[NOTIF] {event_type} → {user.username} (RQ #{pr_id})')

            # --- REALTIME BROADCAST ---
            # Notificar via WebSocket imediatamente para feedback visual/sonoro
            payload = {
                'id': pr_id,
                'message': message,
                'event_type': event_type
            }
            
            # Mapear eventos internos para tipos que o Frontend espera
            ws_type = 'purchase_request.status_changed'
            if event_type == 'RQ_SUBMITTED':
                ws_type = 'purchase_request.assigned_to_me'
            elif event_type == 'RQ_APPROVED_FINAL':
                ws_type = 'purchase_request.approved'
            elif event_type == 'RQ_REJECTED_DEPT':
                ws_type = 'purchase_request.rejected'

            self._broadcast_realtime(user, ws_type, payload)
            # --------------------------
        except IntegrityError:
            # Deduplicação: já existe uma notificação com esta key
            logger.debug(f'[NOTIF] Duplicado ignorado: {notification_key}')
        except Exception as e:
            logger.error(f'[NOTIF] Erro ao criar notificação para {user.username}: {e}')

    def _send_email_safe(self, user, subject, template, context):
        """
        Envia email de forma assíncrona (background thread).
        O template é renderizado de forma síncrona (precisa do contexto Django),
        mas o envio SMTP é feito em background para não bloquear o HTTP response.
        """
        if not user.email:
            logger.warning(f'[EMAIL] Utilizador {user.username} sem email configurado — notificação não enviada')
            return

        try:
            # Garantir que o site_url e contactos estejam no contexto para o base.html
            context['site_url'] = self.site_url
            context['contacts'] = getattr(settings, 'ENGCONSULT_CONTACTS', {})
            
            # Renderizar template de forma síncrona (precisa do ORM)
            html_message = render_to_string(template, context)
            plain_message = strip_tags(html_message)
        except Exception as e:
            logger.error(f'[EMAIL] Erro ao renderizar template {template}: {e}')
            return

        # Enviar em background thread
        def _send():
            try:
                send_mail(
                    subject=subject,
                    message=plain_message,
                    from_email=self.from_email,
                    recipient_list=[user.email],
                    html_message=html_message,
                    fail_silently=False,
                )
                logger.info(f'[EMAIL] Enviado para {user.email}: {subject}')
            except Exception as e:
                logger.error(f'[EMAIL] Falha ao enviar para {user.email}: {e}')

        thread = threading.Thread(target=_send, daemon=True)
        thread.start()

    def _broadcast_realtime(self, user, event_type, payload):
        """
        Envia evento para o grupo privado do utilizador via Channel Layer (WebSocket).
        """
        try:
            channel_layer = get_channel_layer()
            group_name = f"user_{user.id}"
            
            async_to_sync(channel_layer.group_send)(
                group_name,
                {
                    'type': 'purchase_request_event',
                    'data': {
                        'type': event_type,
                        'payload': payload,
                        'timestamp': timezone.now().isoformat()
                    }
                }
            )
            logger.debug(f'[WS] Evento {event_type} enviado para {group_name}')
        except Exception as e:
            logger.error(f'[WS] Falha ao enviar broadcast para user_{user.id}: {e}')
    def _broadcast_realtime_to_group(self, group_name, event_type, payload):
        """
        Envia evento para um grupo arbitrário (ex: 'purchase_requests' global).
        """
        try:
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            from django.utils import timezone
            
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                group_name,
                {
                    'type': 'purchase_request_event',
                    'data': {
                        'type': event_type,
                        'payload': payload,
                        'timestamp': timezone.now().isoformat()
                    }
                }
            )
            logger.debug(f'[WS] Evento {event_type} enviado para Grupo {group_name}')
        except Exception as e:
            logger.error(f'[WS] Falha ao enviar broadcast para Grupo {group_name}: {e}')

    def notify_item_updated(self, purchase_request, actor=None):
        """
        Evento: ITEM_UPDATED
        Emite um evento global via WS para que as tabelas atualizem.
        """
        payload = {
            'id': purchase_request.id,
            'code': purchase_request.code,
            'message': f'Itens da requisição #{purchase_request.code} foram atualizados.',
            'actor': actor.get_full_name() if actor else 'Central'
        }
        self._broadcast_realtime_to_group('purchase_requests', 'purchase_request.item_updated', payload)
