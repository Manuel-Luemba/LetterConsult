from typing import List, Optional
from django.shortcuts import get_object_or_404
from ninja import Router, File, Form
from ninja.files import UploadedFile
from django.core.mail import send_mail
from django.conf import settings
from .models import JobVacancy, JobApplication
from .schemas import VacancyOut, VacancyIn, ApplicationIn
from core.login.jwt_auth import JWTAuth

router = Router(tags=["Recrutamento"])

# --- PUBLIC ENDPOINTS ---

@router.get("/vacancies", response=List[VacancyOut])
def list_vacancies(request):
    return JobVacancy.objects.filter(is_active=True).order_by("-id")

@router.get("/vacancies/{vacancy_id}", response=VacancyOut)
def get_vacancy(request, vacancy_id: int):
    return get_object_or_404(JobVacancy, id=vacancy_id)

@router.post("/apply")
def submit_application(
    request, 
    payload: ApplicationIn = Form(...), 
    cv: UploadedFile = File(...), 
    others: Optional[UploadedFile] = File(None)
):
    vacancy = get_object_or_404(JobVacancy, id=payload.vacancy_id)
    
    application = JobApplication.objects.create(
        vacancy=vacancy,
        full_name=payload.full_name,
        email=payload.email,
        phone=payload.phone,
        academic_degree=payload.academic_degree,
        message=payload.message,
        cv_file=cv,
        other_files=others
    )
    
    # Notificação por Email
    send_mail(
        subject=f"Nova Candidatura: {vacancy.title} - {payload.full_name}",
        message=f"Nome: {payload.full_name}\nEmail: {payload.email}\nTelefone: {payload.phone}\nVaga: {vacancy.title}",
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=['recursoshumanos@engconsult-ao.com'],
        fail_silently=True,
    )
    
    return {"success": True, "id": application.id}

# --- ADMIN ENDPOINTS (Require Auth) ---

@router.get("/admin/vacancies", response=List[VacancyOut], auth=JWTAuth())
def list_vacancies_admin(request):
    return JobVacancy.objects.all().order_by("-id")

@router.post("/vacancies/create", response=VacancyOut, auth=JWTAuth())
def create_vacancy(request, payload: VacancyIn):
    vacancy = JobVacancy.objects.create(**payload.dict())
    return vacancy

@router.put("/vacancies/{vacancy_id}", response=VacancyOut, auth=JWTAuth())
def update_vacancy(request, vacancy_id: int, payload: VacancyIn):
    vacancy = get_object_or_404(JobVacancy, id=vacancy_id)
    for attr, value in payload.dict().items():
        setattr(vacancy, attr, value)
    vacancy.save()
    return vacancy

@router.get("/admin/applications", response=List[dict], auth=JWTAuth())
def list_applications_admin(request):
    # Usamos select_related para performance ao buscar o título da vaga
    apps = JobApplication.objects.select_related('vacancy').all().order_by("-created_at")
    return [{
        "id": a.id,
        "vacancy": a.vacancy.title,
        "name": a.full_name,
        "email": a.email,
        "date": a.created_at.strftime("%Y-%m-%d"),
        "cv": a.cv_file.url if a.cv_file else None
    } for a in apps]
