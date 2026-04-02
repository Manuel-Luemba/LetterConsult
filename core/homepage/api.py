from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404
from ninja import Router
from ninja.errors import HttpError
from .models import Position, ContactLead
from .schemas import PositionIn, PositionOut, PaginatedPositionResponse, ContactIn, ContactStatsOut
from core.login.jwt_auth import JWTAuth
from django.core.mail import send_mail
from app import settings

router = Router(tags=["Positions"], auth=JWTAuth())

def check_admin(request):
    if not getattr(request.auth, 'is_administrator', False):
        raise HttpError(403, "Apenas administradores podem executar esta ação.")


# ------------------------------------------------------------
# CREATE
# ------------------------------------------------------------
@router.post("/create", response=PositionOut)
def create_position(request, payload: PositionIn):
    check_admin(request)
    position = Position.objects.create(
        name=payload.name,
        desc=payload.desc
    )
    return PositionOut(id=position.id, name=position.name)


# ------------------------------------------------------------
# LIST PAGINATED
# ------------------------------------------------------------
@router.get("/list", response=PaginatedPositionResponse)
def get_positions_paginated(request, page: int = 1, page_size: int = 15):
    try:
        queryset = Position.objects.all().order_by("-id")

        paginator = Paginator(queryset, page_size)
        current_page = paginator.get_page(page)

        items = [
            PositionOut(id=p.id, name=p.name)
            for p in current_page
        ]

        return {
            "count": paginator.count,
            "total_pages": paginator.num_pages,
            "current_page": current_page.number,
            "page_size": page_size,
            "has_next": current_page.has_next(),
            "has_prev": current_page.has_previous(),
            "items": items,
        }

    except Exception as e:
        raise HttpError(500, "Erro ao carregar posições")


# ------------------------------------------------------------
# GET BY ID
# ------------------------------------------------------------
@router.get("/{position_id}", response=PositionOut)
def get_position(request, position_id: int):
    position = get_object_or_404(Position, id=position_id)
    return PositionOut(id=position.id, name=position.name)


# ------------------------------------------------------------
# UPDATE
# ------------------------------------------------------------
@router.put("/{position_id}", response=PositionOut)
def update_position(request, position_id: int, payload: PositionIn):
    check_admin(request)
    position = get_object_or_404(Position, id=position_id)

    position.name = payload.name
    position.desc = payload.desc
    position.save()

    return PositionOut(id=position.id, name=position.name)


# ------------------------------------------------------------
# DELETE
# ------------------------------------------------------------
@router.delete("/{position_id}")
def delete_position(request, position_id: int):
    check_admin(request)
    position = get_object_or_404(Position, id=position_id)
    position.delete()

    return {"success": True}

# ------------------------------------------------------------
# PUBLIC ROUTER - CONTACT FORM (SECURE VERSION)
# ------------------------------------------------------------
from ninja import Router as PublicRouter
from django.utils.html import strip_tags
import time
from django.core.cache import cache

contact_router = PublicRouter(tags=["Contact"], auth=None)


def rate_limit_check(ip):
    cache_key = f"contact_limit_{ip}"
    requests = cache.get(cache_key, 0)
    if requests >= 5: # Limite de 5 mensagens por hora
        return False
    cache.set(cache_key, requests + 1, 3600) # Reset após 1 hora
    return True

@contact_router.post("/")
def submit_contact(request, payload: ContactIn):
    # 1. Proteção Bot (Honeypot no Backend)
    if payload.website:
        return {"success": True, "message": "Bot filtered"}

    # 2. Rate Limiting (Proteção Anti-Spam)
    user_ip = request.META.get('REMOTE_ADDR')
    if not rate_limit_check(user_ip):
        return 429, {"message": "Limite de envios excedido. Tente novamente mais tarde."}

    # 3. Sanitização de Scripts (Anti-XSS)
    clean_name = strip_tags(payload.full_name)
    clean_message = strip_tags(payload.message)
    
    # 4. Salvar na Base de Dados
    ContactLead.objects.create(
        full_name=clean_name,
        email=payload.email,
        phone=payload.phone,
        message=clean_message
    )
    
    # 5. Enviar Notificação por E-mail
    try:
        subject = f"Novo Contacto: {clean_name}"
        email_message = f"Nome: {clean_name}\nEmail: {payload.email}\nTelefone: {payload.phone}\n\nMensagem:\n{clean_message}"
        send_mail(
            subject,
            email_message,
            settings.DEFAULT_FROM_EMAIL,
            ['geral@engconsult-ao.com', 'recursoshumanos@engconsult-ao.com'],
            fail_silently=True,
        )
    except:
        pass
        
    return {"success": True, "message": "Mensagem enviada com sucesso"}


@contact_router.get("/stats/", response=ContactStatsOut)
def get_contact_stats(request):
    """
    Returns representative static statistics for the company.
    """
    return ContactStatsOut(
        men_pct=60,
        women_pct=40,
        higher_ed_pct=75
    )