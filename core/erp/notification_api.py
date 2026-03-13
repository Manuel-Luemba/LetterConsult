# core/erp/notification_api.py
"""
Router dedicado para notificações.
Registado em /api/v1/notifications/ para evitar conflitos de rotas.
"""
from typing import List, Optional
from datetime import datetime
from ninja import Router, Schema
from django.shortcuts import get_object_or_404

from .models import Notification

router = Router(tags=["Notifications"])


# ============================================
# SCHEMAS
# ============================================

class NotificationOut(Schema):
    id: int
    message: str
    event_type: str
    purchase_request_id: Optional[int] = None
    action_url: str = ''
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True


class UnreadCountOut(Schema):
    count: int


# ============================================
# ENDPOINTS
# ============================================

@router.get("", response=List[NotificationOut])
def list_notifications(request):
    """
    Lista as últimas 30 notificações do utilizador autenticado.
    """
    user = request.auth
    qs = Notification.objects.filter(user=user).order_by('-created_at')[:30]
    return list(qs)


@router.get("/unread-count", response=UnreadCountOut)
def unread_count(request):
    """
    Retorna a contagem de notificações não lidas.
    """
    user = request.auth
    count = Notification.objects.filter(user=user, is_read=False).count()
    return {"count": count}


@router.post("/{notification_id}/read")
def mark_as_read(request, notification_id: int):
    """
    Marca uma notificação como lida.
    """
    notification = get_object_or_404(Notification, id=notification_id, user=request.auth)
    notification.is_read = True
    notification.save()
    return {"success": True}


@router.post("/{notification_id}/unread")
def mark_as_unread(request, notification_id: int):
    """
    Marca uma notificação como não lida.
    """
    notification = get_object_or_404(Notification, id=notification_id, user=request.auth)
    notification.is_read = False
    notification.save()
    return {"success": True}


@router.delete("/{notification_id}")
def delete_notification(request, notification_id: int):
    """
    Elimina uma notificação específica.
    """
    notification = get_object_or_404(Notification, id=notification_id, user=request.auth)
    notification.delete()
    return {"success": True}


@router.post("/read-all")
def mark_all_as_read(request):
    """
    Marca todas as notificações do utilizador como lidas.
    """
    user = request.auth
    updated = Notification.objects.filter(user=user, is_read=False).update(is_read=True)
    return {"success": True, "updated": updated}


@router.delete("/clear-all")
def clear_all_notifications(request):
    """
    Elimina todas as notificações do utilizador.
    """
    user = request.auth
    deleted, _ = Notification.objects.filter(user=user).delete()
    return {"success": True, "deleted": deleted}
