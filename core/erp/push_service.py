import json
import logging
from pywebpush import webpush, WebPushException
from django.conf import settings

logger = logging.getLogger(__name__)

def send_user_notification_push(user, message, action_url=""):
    """
    Envia notificações push (Native Browser) para todos os dispositivos 
    registados do utilizador.
    """
    subscriptions = user.push_subscriptions.all()
    if not subscriptions.exists():
        return

    payload = {
        "title": "ERP Engconsult",
        "body": message,
        "data": {
            "url": action_url or settings.SITE_URL
        },
        "icon": "/logo.png", # Ajustar conforme assets do frontend
        "badge": "/badge.png"
    }
    
    for sub in subscriptions:
        try:
            webpush(
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": {
                        "p256dh": sub.p256dh,
                        "auth": sub.auth
                    }
                },
                data=json.dumps(payload),
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims={
                    "sub": f"mailto:{settings.VAPID_CLAIM_EMAIL}"
                }
            )
            logger.info(f"[PUSH] Enviado com sucesso para {user.username} ({sub.browser})")
        except WebPushException as ex:
            logger.warning(f"[PUSH] Erro ao enviar para {user.username}: {ex}")
            # Se a subscrição expirou ou o endpoint não existe mais (410 Gone / 404 Not Found)
            if ex.response and ex.response.status_code in [404, 410]:
                logger.info(f"[PUSH] Removendo subscrição inválida de {user.username}")
                sub.delete()
        except Exception as e:
            logger.error(f"[PUSH] Erro inesperado: {e}")
