import logging
from django.core.mail import send_mail
from django.conf import settings
from .push_service import send_user_notification_push
from core.user.models import User

logger = logging.getLogger(__name__)

def send_email_task(subject, plain_message, from_email, recipient_list, html_message=None):
    """
    Tarefa assíncrona para envio de emails via Django Q.
    """
    try:
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=from_email,
            recipient_list=recipient_list,
            html_message=html_message,
            fail_silently=False,
        )
        logger.info(f"[TASK-EMAIL] Enviado com sucesso para {recipient_list}")
    except Exception as e:
        logger.error(f"[TASK-EMAIL] Falha ao enviar para {recipient_list}: {e}")

def send_webpush_task(user_id, message, action_url=""):
    """
    Tarefa assíncrona para envio de Web Push via Django Q.
    """
    try:
        user = User.objects.get(id=user_id)
        send_user_notification_push(user, message, action_url)
        logger.info(f"[TASK-PUSH] Processado para o utilizador ID {user_id}")
    except User.DoesNotExist:
        logger.error(f"[TASK-PUSH] Utilizador ID {user_id} não encontrado")
    except Exception as e:
        logger.error(f"[TASK-PUSH] Erro ao processar push para utilizador ID {user_id}: {e}")
