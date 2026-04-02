from django.db.models.signals import post_save
from django.dispatch import receiver
from django_q.tasks import async_task
from .models import Notification
from .tasks import send_webpush_task

@receiver(post_save, sender=Notification)
def trigger_notification_push(sender, instance, created, **kwargs):
    """
    Sinal que dispara um Web Push em background sempre que uma nova 
    notificação é criada.
    """
    if created:
        try:
            # Envia a tarefa para a fila do Django Q
            async_task(
                'core.erp.tasks.send_webpush_task',
                user_id=instance.user.id,
                message=instance.message,
                action_url=instance.action_url
            )
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"[SIGNAL] Erro ao enfileirar push para Notificação #{instance.id}: {e}")

