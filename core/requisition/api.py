# api/endpoints.py
from ninja import Router, File
from ninja.files import UploadedFile
from ninja.pagination import paginate, PageNumberPagination
from typing import List
from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.utils import timezone
from datetime import timedelta
import logging
import os

logger = logging.getLogger(__name__)
from core.login.jwt_auth import JWTAuth
from .models import PurchaseRequest, PurchaseRequestItem, Attachment, Supplier, ItemCategory, Approval, PurchaseRequestAssignment
from .schemas import *
from core.requisition.schemas import BulkActionRequest, BulkActionResponse

from .services.PurchasingAnalysisService import PurchasingAnalysisService
from .services.workflow_service import WorkflowService
from ..erp.models import Department
from ..project.models import Project
from .schemas import AnalyzeResponse

router = Router(tags=["Requisition"], auth=JWTAuth())


# ============================================
# STATUS GROUPS (Requester Context)
# ============================================
REQUESTER_PENDING_STATUSES = [
    'PENDING_PROJECT_APPROVAL', 'PENDING_DEPARTMENT_APPROVAL', 
    'PENDING_PURCHASING', 'PENDING_DIRECTOR_APPROVAL', 
    'AWAITING_REQUESTER_DECISION', 'PARTIALLY_APPROVED'
]
REQUESTER_APPROVED_STATUSES = [
    'APPROVED', 'ORDERED', 'PARTIALLY_RECEIVED', 'COMPLETED'
]
REQUESTER_REJECTED_STATUSES = [
    'REJECTED', 'CANCELLED'
]

# ============================================
# AVAILABLE CONTEXTS
# ============================================

@router.get("/available-contexts", response=List[dict])
def get_available_contexts(request):
    """
    Retorna contextos disponíveis para o utilizador criar requisições
    """
    user = request.auth
    contexts = []

    # 1. Departamental (sempre disponível se tem departamento)
    if user.department and user.department.is_active:
        contexts.append({
            'type': 'DEPARTMENT',
            'label': 'Requisição Departamental',
            'department': {'id': user.department.id, 'name': user.department.name}
        })

    # 2. Projetos onde o user está alocado
    active_projects = Project.objects.filter(is_active=True)

    # Team Leader
    for project in active_projects.filter(team_leader=user):
        contexts.append({
            'type': 'PROJECT',
            'label': f'Requisição de Projeto - {project.name}',
            'project': {'id': project.id, 'name': project.name, 'cost_center': project.cost_center}
        })

    # Responsável
    for project in active_projects.filter(responsible=user):
        contexts.append({
            'type': 'PROJECT',
            'label': f'Requisição de Projeto - {project.name}',
            'project': {'id': project.id, 'name': project.name, 'cost_center': project.cost_center}
        })

    # Administrativo
    for project in active_projects.filter(administrative_staff=user):
        contexts.append({
            'type': 'PROJECT',
            'label': f'Requisição de Projeto - {project.name}',
            'project': {'id': project.id, 'name': project.name, 'cost_center': project.cost_center}
        })

    return contexts

# ============================================
# PURCHASE REQUESTS CRUD
# ============================================

@router.post("/add", response=MessageResponse)
def create_purchase_request(request, payload: PurchaseRequestCreate):
    """
    Criar nova requisição de compra
    """
    user = request.auth

    # Validar contexto
    project = None
    department = None

    if payload.context_type == 'PROJECT':
        project = get_object_or_404(Project, id=payload.project_id)
        if not project.user_belongs_to_project(user):
            return 403, {"message": "Você não está alocado neste projeto"}
        department = project.department
    else:
        if payload.department_id:
            department = get_object_or_404(Department, id=payload.department_id)
        else:
            department = user.department

        if not department:
            return 400, {"message": "Departamento não especificado"}

    # Criar requisição
    purchase_request = PurchaseRequest.objects.create(
        context_type=payload.context_type,
        project=project,
        department=department,
        requested_by=user,
        required_date=payload.required_date,
        reference_month=payload.reference_month,
        justification=payload.justification,
        observations=payload.observations,
        status='DRAFT'
    )

    # Criar itens
    total = 0
    for item_data in payload.items:
        item = PurchaseRequestItem.objects.create(
            purchase_request=purchase_request,
            description=item_data.description,
            quantity=item_data.quantity,
            unit_price=item_data.unit_price,
            urgency_level=item_data.urgency_level,
            preferred_supplier=(item_data.preferred_supplier.strip() if getattr(item_data, 'preferred_supplier', None) and isinstance(item_data.preferred_supplier, str) else None),
            supplier_id=getattr(item_data, 'supplier_id', None),
            delivery_deadline=getattr(item_data, 'delivery_deadline', None),
            special_status=item_data.special_status,
            observations=item_data.observations,
            tax_rate=getattr(item_data, 'tax_rate', None),
            base_price=getattr(item_data, 'base_price', None)
        )
        if item.total_price:
            total += item.total_price

    # Atualizar total
    purchase_request.total_amount = total
    purchase_request.save()

    return 200, {"message": "Requisição criada com sucesso", "id": purchase_request.id}

@router.get("/counts", response=dict)
def get_requisition_counts(request, assigned_to_me: bool = False, assignment_status: str = None, is_urgent: bool = False, overdue: bool = False):
    """
    Retorna a contagem de requisições baseada nos mesmos filtros rápidos.
    """
    user = request.auth
    queryset = PurchaseRequest.objects.all()

    # 1. Filtragem de Permissões (igual ao /list)
    if not user.is_administrator:
        if user.is_purchasing_central:
            queryset = queryset.filter(
                Q(status__in=['PENDING_PURCHASING', 'PENDING_DIRECTOR_APPROVAL', 'APPROVED', 'REJECTED']) |
                Q(requested_by=user)
            )
        elif user.is_director or user.is_deputy_director:
            queryset = queryset.filter(
                Q(status__in=['PENDING_DIRECTOR_APPROVAL', 'APPROVED', 'REJECTED']) |
                Q(requested_by=user)
            )
        else:
            queryset = queryset.filter(
                Q(requested_by=user) | 
                Q(assignments__approver=user)
            ).distinct()

    # 2. Filtro assigned_to_me / assignment_status (igual ao /list)
    if assigned_to_me or assignment_status:
        if user.is_purchasing_central:
            if assignment_status == 'COMPLETED':
                 queryset = queryset.filter(approvals__approver=user, approvals__action__in=['APPROVE', 'FORWARD'])
            elif assignment_status == 'REJECTED':
                 queryset = queryset.filter(approvals__approver=user, approvals__action='REJECT')
            else:
                 queryset = queryset.filter(status='PENDING_PURCHASING')
        elif user.is_director or user.is_deputy_director:
            if assignment_status == 'COMPLETED':
                 queryset = queryset.filter(approvals__approver=user, approvals__action='APPROVE')
            elif assignment_status == 'REJECTED':
                 queryset = queryset.filter(approvals__approver=user, approvals__action='REJECT')
            else:
                 queryset = queryset.filter(status='PENDING_DIRECTOR_APPROVAL')
        else:
            status_to_filter = assignment_status if assignment_status else 'PENDING'
            queryset = queryset.filter(assignments__approver=user, assignments__status=status_to_filter).distinct()

    # 3. Filtros Rápidos
    if is_urgent:
        from datetime import timedelta
        limit_date = timezone.now().date() + timedelta(days=2)
        queryset = queryset.filter(
            Q(items__urgency_level__in=['HIGH', 'CRITICAL']) |
            Q(required_date__isnull=False, required_date__lte=limit_date)
        ).exclude(
            # Contadores (Badges) focam apenas no que é acionável (atualmente em aberto)
            status__in=REQUESTER_APPROVED_STATUSES + REQUESTER_REJECTED_STATUSES
        ).distinct()

    if overdue:
        today = timezone.now().date()
        queryset = queryset.filter(
            required_date__lt=today
        ).exclude(
            # Contadores (Badges) focam apenas no que é acionável (atualmente em aberto)
            status__in=REQUESTER_APPROVED_STATUSES + REQUESTER_REJECTED_STATUSES
        )
        
    return {"count": queryset.count()}


@router.get("/counts-by-status", response=dict)
def get_counts_by_status(request, role_context: str = 'requester'):
    """
    Retorna contagem de requisições agrupadas por status.
    role_context: 'requester' (Minhas RCs) ou 'approver' (Minhas Aprovações)
    """
    user = request.auth

    if role_context == 'approver':
        # Base: Tudo onde eu tenho um assignment ou já aprovei/rejeitei
        base_qs = PurchaseRequest.objects.filter(
            Q(assignments__approver=user) | Q(approvals__approver=user)
        ).distinct()
        
        return {
            "all": base_qs.count(),
            "pending": base_qs.filter(assignments__approver=user, assignments__status='PENDING').distinct().count(),
            "approved": base_qs.filter(approvals__approver=user, approvals__action='APPROVE').distinct().count(),
            "rejected": base_qs.filter(approvals__approver=user, approvals__action='REJECT').distinct().count(),
            "draft": 0, # Aprovações não têm rascunho
        }
    else:
        # Contar apenas as requisições submetidas pelo próprio utilizador (Padrão)
        my_requests = PurchaseRequest.objects.filter(requested_by=user)
        return {
            "all": my_requests.count(),
            "pending": my_requests.filter(status__in=REQUESTER_PENDING_STATUSES).count(),
            "approved": my_requests.filter(status__in=REQUESTER_APPROVED_STATUSES).count(),
            "rejected": my_requests.filter(status__in=REQUESTER_REJECTED_STATUSES).count(),
            "draft": my_requests.filter(status='DRAFT').count(),
        }



@router.get("/list", response=List[PurchaseRequestSchema])
@paginate(PageNumberPagination, page_size=20)
def list_purchase_requests(request, status: str = None, context: str = None, urgency: str = None, 
                           search: str = None, tab: str = None, 
                           role_context: str = 'requester',
                           edited_by_purchasing: bool = False, is_urgent: bool = False, overdue: bool = False,
                           reference_month: str = None, cost_center: str = None):
    """
    Listar requisições (com filtros)
    """
    user = request.auth
    queryset = PurchaseRequest.objects.all()

    # 1. Filtrar por contexto de papel (Solicitante vs Aprovador)
    if role_context == 'requester':
        queryset = queryset.filter(requested_by=user)
    elif role_context == 'approver':
        queryset = queryset.filter(
            Q(assignments__approver=user) | Q(approvals__approver=user)
        ).distinct()
    else:
        # Fallback de permissões base se nenhum contexto for passado
        if not user.is_administrator:
            if user.is_purchasing_central:
                queryset = queryset.filter(
                    Q(status__in=['PENDING_PURCHASING', 'PENDING_DIRECTOR_APPROVAL', 'APPROVED', 'REJECTED']) |
                    Q(requested_by=user)
                )
            elif user.is_director or user.is_deputy_director:
                queryset = queryset.filter(
                    Q(status__in=['PENDING_DIRECTOR_APPROVAL', 'APPROVED', 'REJECTED']) |
                    Q(requested_by=user)
                )
            else:
                queryset = queryset.filter(
                    Q(requested_by=user) | Q(assignments__approver=user)
                ).distinct()

    # 2. Lógica de ABAS (Status/Ações)
    if tab:
        if tab == 'pending':
            if role_context == 'approver':
                queryset = queryset.filter(assignments__approver=user, assignments__status='PENDING').distinct()
            else:
                queryset = queryset.filter(status__in=REQUESTER_PENDING_STATUSES)
        elif tab == 'approved':
            if role_context == 'approver':
                queryset = queryset.filter(approvals__approver=user, approvals__action='APPROVE').distinct()
            else:
                queryset = queryset.filter(status__in=REQUESTER_APPROVED_STATUSES)
        elif tab == 'rejected':
            if role_context == 'approver':
                queryset = queryset.filter(approvals__approver=user, approvals__action='REJECT').distinct()
            else:
                queryset = queryset.filter(status__in=REQUESTER_REJECTED_STATUSES)
        elif tab == 'draft':
            queryset = queryset.filter(status='DRAFT')

    # 3. Filtros Adicionais (Específicos da RC)
    if status:
        queryset = queryset.filter(status=status)
    if context:
        queryset = queryset.filter(context_type=context)
    if reference_month:
        queryset = queryset.filter(reference_month=reference_month)
    if cost_center:
        queryset = queryset.filter(cost_center__icontains=cost_center)
    if urgency:
        queryset = queryset.filter(urgency_level=urgency)

    # 4. Filtros Rápidos (Urgentes e Atrasadas)
    if is_urgent:
        # Próximo da data (2 dias) ou marcado como urgente/crítico
        limit_date = timezone.now().date() + timedelta(days=2)
        queryset = queryset.filter(
            Q(items__urgency_level__in=['HIGH', 'CRITICAL']) |
            Q(required_date__isnull=False, required_date__lte=limit_date)
        ).distinct() # Nota: Na listagem permitimos ver urgentes mesmo aprovadas (Histórico)
        
    if overdue:
        # A data necessária já passou
        today = timezone.now().date()
        queryset = queryset.filter(
            required_date__lt=today
        ) # Nota: Na listagem permitimos ver atrasadas mesmo aprovadas (Histórico)

    # 5. Busca Livre
    if search:
        queryset = queryset.filter(
            Q(code__icontains=search) |
            Q(requested_by__full_name__icontains=search) |
            Q(requested_by__username__icontains=search) |
            Q(items__description__icontains=search) |
            Q(justification__icontains=search) |
            Q(erp_reference__icontains=search) |
            Q(cost_center__icontains=search)
        ).distinct()

    # 6. Anotações para UI (Can Approve, My Assignment)
    from django.db.models import Case, When, Value, BooleanField, Subquery, OuterRef

    can_approve_q = Q()
    if getattr(user, 'is_purchasing_central', False):
        can_approve_q |= Q(status='PENDING_PURCHASING')
    if getattr(user, 'is_director', False) or getattr(user, 'is_deputy_director', False):
        can_approve_q |= Q(status='PENDING_DIRECTOR_APPROVAL')

    # Se o utilizar tem assignment PENDING, também pode aprovar
    can_approve_q |= Q(assignments__approver=user, assignments__status='PENDING')

    my_assignment = PurchaseRequestAssignment.objects.filter(
        purchase_request=OuterRef('pk'),
        approver=user
    ).order_by('-assigned_at')

    queryset = queryset.annotate(
        annotated_can_approve=Case(
            When(can_approve_q, then=Value(True)),
            default=Value(False),
            output_field=BooleanField()
        ),
        annotated_my_assignment_status=Subquery(my_assignment.values('status')[:1]),
        annotated_my_assignment_id=Subquery(my_assignment.values('id')[:1])
    )

    return queryset.distinct().order_by('-created_at')

@router.get("/suppliers", response=List[SupplierSchema])
def list_suppliers(request, search: Optional[str] = None):
    """
    Lista fornecedores ativos. Permite busca por nome ou código.
    """
    qs = Supplier.objects.filter(is_active=True)
    if search:
        qs = qs.filter(Q(name__icontains=search) | Q(code__icontains=search))
    return list(qs)

@router.post("/suppliers", response={201: SupplierSchema, 400: MessageResponse})
def create_supplier(request, payload: SupplierCreateSchema):
    """
    Cria um novo fornecedor.
    """
    if Supplier.objects.filter(code=payload.code).exists():
        return 400, {"message": "Já existe um fornecedor com este código."}
    supplier = Supplier.objects.create(**payload.dict())
    return 201, supplier

@router.get("/{request_id}", response=PurchaseRequestSchema)
def get_purchase_request(request, request_id: int):
    """
    Detalhe de uma requisição
    """
    purchase_request = get_object_or_404(PurchaseRequest, id=request_id)
    purchase_request._current_user = request.auth  # Injectar user para contornar contexto do Ninja

    # Verificar permissão
    user = request.auth

    # Administradores e Central de Compras veem tudo
    if user.is_administrator or user.is_purchasing_central:
        return 200, purchase_request

    # O próprio solicitante
    if purchase_request.requested_by == user:
        return 200, purchase_request

    # Diretores/Adjuntos veem requisições em qualquer estado
    if user.is_director or user.is_deputy_director:
        return 200, purchase_request

    # Aprovadores de PROJETO (responsáveis, team leaders, etc.)
    if purchase_request.context_type == 'PROJECT' and purchase_request.project:
        if user in purchase_request.all_possible_approvers_for_project_request():
            return 200, purchase_request

    # Aprovadores de DEPARTAMENTO (manager, adjunto)
    if purchase_request.department:
        if user in purchase_request.department.all_approvers:
            return 200, purchase_request

    # Utilizador com assignment pendente (inbox)
    if purchase_request.assignments.filter(approver=user).exists():
        return 200, purchase_request

    return 403, {"message": "Sem permissão para ver esta requisição"}


@router.put("/{request_id}", response=MessageResponse)
def update_purchase_request(request, request_id: int, payload: PurchaseRequestUpdate):
    """
    Atualizar requisição (apenas em rascunho)
    """
    purchase_request = get_object_or_404(PurchaseRequest, id=request_id)
    user = request.auth

    # Verificar permissão
    if purchase_request.requested_by != user and not user.is_administrator:
        return 403, {"message": "Apenas o solicitante pode editar"}

    if purchase_request.status != 'DRAFT':
        return 400, {"message": f"Não é possível editar requisição com status {purchase_request.status}"}

    # Atualizar campos
    for field in ['required_date', 'justification', 'observations']:
        if getattr(payload, field, None):
            setattr(purchase_request, field, getattr(payload, field))

    purchase_request.save()

    # Atualizar itens (se fornecidos)
    if payload.items:
        # Remover itens existentes
        purchase_request.items.all().delete()

        # Criar novos
        total = 0
        for item_data in payload.items:
            item = PurchaseRequestItem.objects.create(
                purchase_request=purchase_request,
                description=item_data.description,
                quantity=item_data.quantity,
                unit_price=item_data.unit_price,
                urgency_level=item_data.urgency_level,
                preferred_supplier=(item_data.preferred_supplier.strip() if getattr(item_data, 'preferred_supplier', None) and isinstance(item_data.preferred_supplier, str) else None),
                supplier_id=getattr(item_data, 'supplier_id', None),
                delivery_deadline=getattr(item_data, 'delivery_deadline', None),
                special_status=item_data.special_status,
                observations=item_data.observations,
                tax_rate=getattr(item_data, 'tax_rate', None),
                base_price=getattr(item_data, 'base_price', None)
            )
            if item.total_price:
                total += item.total_price

        purchase_request.total_amount = total
        purchase_request.save()

    return 200, {"message": "Requisição atualizada com sucesso"}

@router.post("/{request_id}/clone/", response=PurchaseRequestSchema)
def clone_purchase_request(request, request_id: int, payload: CloneRequestPayload):
    """
    Clonar uma requisição de compra existente para criar um novo rascunho.
    """
    original = get_object_or_404(PurchaseRequest, id=request_id)
    user = request.auth

    # Verificar permissão (Criador, Admin ou Central)
    if not (original.requested_by == user or user.is_administrator or user.is_purchasing_central):
        return 403, {"message": "Sem permissão para clonar esta requisição"}

    from django.db import transaction
    with transaction.atomic():
        # 1. Clonar a Requisição base
        new_request = PurchaseRequest.objects.create(
            context_type=original.context_type,
            project=original.project,
            department=original.department,
            business_unit=original.business_unit,
            requested_by=user,  # O novo rascunho pertence a quem clonou
            required_date=original.required_date,
            reference_month=original.reference_month,
            status='DRAFT',
            cost_center=original.cost_center,
            total_amount=original.total_amount,
            justification=original.justification,
            observations=f"(Clonada da {original.code})\n{original.observations}" if original.observations else f"Clonada da {original.code}",
        )

        # 2. Clonar Itens
        for item in original.items.all():
            PurchaseRequestItem.objects.create(
                purchase_request=new_request,
                description=item.description,
                urgency_level=item.urgency_level,
                quantity=item.quantity,
                unit_price=item.unit_price,
                tax_rate=item.tax_rate,
                base_price=item.base_price,
                preferred_supplier=item.preferred_supplier,
                supplier_id=item.supplier_id,
                special_status=item.special_status,
                observations=item.observations,
                delivery_deadline=item.delivery_deadline
            )

        # 3. Clonar Anexos (opcional)
        if payload.include_attachments:
            for att in original.attachments.all():
                # Criar nova instância copiando o ficheiro
                new_att = Attachment(
                    purchase_request=new_request,
                    attachment_type=att.attachment_type,
                    description=att.description,
                    uploaded_by=user,
                    filename=att.filename,
                    file_size=att.file_size
                )
                if att.file:
                    # Copiar o ficheiro físico
                    from django.core.files.base import ContentFile
                    new_att.file.save(att.filename, ContentFile(att.file.read()), save=False)
                new_att.save()

    return 200, new_request

# ============================================
# ATTACHMENTS
# ============================================

@router.post("/{request_id}/attachments", response={200: MessageResponse, 403: MessageResponse, 413: MessageResponse, 422: MessageResponse})
def upload_attachment(request, request_id: int, file: UploadedFile = File(...), description: str = None, attachment_type: str = 'OTHER'):
    """
    Fazer upload de um anexo para uma requisição
    """
    purchase_request = get_object_or_404(PurchaseRequest, id=request_id)
    user = request.auth

    # Verificar permissão (apenas solicitante ou Admin ou Central se a requisição estiver pending central)
    can_upload = False
    if purchase_request.requested_by == user or user.is_administrator:
        can_upload = True
    elif user.is_purchasing_central and purchase_request.status == 'PENDING_PURCHASING':
        can_upload = True

    if not can_upload:
        return 403, {"message": "Sem permissão para fazer upload para esta requisição."}

    # Validação de Tamanho (Max 10MB)
    MAX_SIZE = 10 * 1024 * 1024  # 10 MB
    if file.size > MAX_SIZE:
        return 413, {"message": "O ficheiro excede o tamanho máximo permitido de 10MB."}

    # Validação de Tipo MIME
    ALLOWED_MIME_TYPES = [
        'application/pdf',
        'image/jpeg',
        'image/png',
    ]
    
    # Permitir todos os openxmlformats (docx, xlsx, pptx, etc)
    is_openxml = file.content_type and file.content_type.startswith('application/vnd.openxmlformats-officedocument.')
    
    if file.content_type not in ALLOWED_MIME_TYPES and not is_openxml:
        # FIX: Rejeitar ficheiros fora da allowlist com 422
        return 422, {"message": f"Tipo de ficheiro não suportado: {file.content_type}"}

    # Criar anexo
    attachment = Attachment.objects.create(
        purchase_request=purchase_request,
        file=file,
        attachment_type=attachment_type,
        description=description or '',
        uploaded_by=user
    )

    return 200, {"message": "Ficheiro anexado com sucesso", "id": attachment.id}


@router.delete("/{request_id}", response={200: MessageResponse, 400: MessageResponse, 403: MessageResponse})
def delete_request(request, request_id: int):
    """
    Eliminar uma requisição (Apenas se nunca foi submetida)
    """
    purchase_request = get_object_or_404(PurchaseRequest, id=request_id)
    user = request.auth

    if purchase_request.requested_by != user and not getattr(user, 'is_administrator', False):
         return 403, {"message": "Sem permissão para eliminar esta requisição."}

    # SE JÁ TEVE SUBMISSÕES (Auditoria / Central de Compras já viu) -> Bloquear!
    if purchase_request.submitted_at is not None:
         return 400, {"message": "Não é possível eliminar uma requisição que já entrou no ciclo de aprovação. Cancele-a em vez disso para manter o histórico."}

    purchase_request.delete()
    return 200, {"message": "Requisição eliminada com sucesso."}


@router.delete("/attachments/{attachment_id}", response={200: MessageResponse, 400: MessageResponse, 403: MessageResponse})
def delete_attachment(request, attachment_id: int):
    """
    Eliminar um anexo
    """
    attachment = get_object_or_404(Attachment, id=attachment_id)
    purchase_request = attachment.purchase_request
    user = request.auth

    # Verificar permissão (apenas quem fez o upload, o próprio solicitante da requisição, ou admin)
    if not (attachment.uploaded_by == user or purchase_request.requested_by == user or user.is_administrator):
        return 403, {"message": "Sem permissão para eliminar este anexo."}
        
    # Verificar estado da requisição (Não permitir remover em requisições aprovadas/concluídas)
    if purchase_request.status in ['APPROVED', 'COMPLETED', 'ORDERED', 'PARTIALLY_RECEIVED', 'CANCELLED']:
         return 400, {"message": f"Não é possível eliminar ficheiros de uma requisição com status {purchase_request.status}."}

    # Eliminar ficheiro físico
    if attachment.file:
        try:
            # FIX: Tentar apagar o ficheiro físico, mas não quebrar se não existir
            file_path = attachment.file.path
            if os.path.isfile(file_path):
                os.remove(file_path)
            else:
                logger.warning(f"Ficheiro não encontrado no sistema para apagar: {file_path}")
        except Exception as e:
            logger.warning(f"Erro ao apagar ficheiro físico do anexo {attachment.id}: {e}")
            
    # Remove database record regardless of physical file deletion success
    attachment.delete()

    return 200, {"message": "Anexo eliminado com sucesso"}

@router.get("/attachments/{attachment_id}/download")
def download_attachment(request, attachment_id: int, token: str):
    """
    Download de um anexo através de um URL pré-assinado (presigned URL)
    """
    user = request.auth  # Garante que o utilizador está autenticado via Router auth=JWTAuth()
    attachment = get_object_or_404(Attachment, id=attachment_id)
    
    # 🔐 Adicional: Verificar se o utilizador tem permissão para ver a requisição deste anexo
    purchase_request = attachment.purchase_request
    
    is_authorized = False
    if user.is_administrator or user.is_purchasing_central or purchase_request.requested_by == user:
        is_authorized = True
    elif user.is_director or user.is_deputy_director:
        is_authorized = True
    elif purchase_request.assignments.filter(approver=user).exists():
        is_authorized = True
    
    if not is_authorized:
         return 403, {"message": "Você não tem permissão para aceder a este ficheiro."}

    signer = TimestampSigner()

    try:
        # Verifica assinatura e garante que tem menos de 30 minutos (1800 segundos)
        original_id = signer.unsign(token, max_age=1800)
        if str(attachment.id) != original_id:
            return 403, {"message": "Token inválido para este anexo."}
    except SignatureExpired:
        return 403, {"message": "O link de download expirou (validade de 30 minutos). Por favor, atualize a página e tente novamente."}
    except BadSignature:
        return 403, {"message": "Link de download inválido."}

    if not attachment.file or not os.path.isfile(attachment.file.path):
        return 404, {"message": "O ficheiro físico não foi encontrado no servidor."}

    content_type, _ = mimetypes.guess_type(attachment.file.name)
    content_type = content_type or 'application/octet-stream'

    response = FileResponse(open(attachment.file.path, 'rb'), content_type=content_type)
    response['Content-Disposition'] = f'attachment; filename="{attachment.filename}"'
    return response

# ============================================
# WORKFLOW ACTIONS
# ============================================

@router.post("/{request_id}/submeter", response=MessageResponse)
def submit_request(request, request_id: int):
    """
    Submeter requisição para aprovação
    """
    purchase_request = get_object_or_404(PurchaseRequest, id=request_id)
    user = request.auth

    if purchase_request.requested_by != user:
        return 403, {"message": "Apenas o solicitante pode submeter"}

    if purchase_request.status != 'DRAFT':
        return 400, {"message": f"Requisição já está com status {purchase_request.status}"}

    # Verificar se tem itens
    if not purchase_request.items.exists():
        return 400, {"message": "Requisição precisa ter pelo menos um item"}

    # Iniciar workflow
    workflow = WorkflowService(purchase_request)
    workflow.submit_for_approval()

    return 200, {"message": "Requisição submetida com sucesso", "status": purchase_request.status}

@router.post("/bulk-submit", response=BulkSubmitResponse)
def bulk_submit_requests(request, payload: BulkSubmitSchema):
    """
    Submeter múltiplas requisições em lote
    """
    user = request.auth
    successful_ids = []
    failed_count = 0
    
    from django.db import transaction
    
    with transaction.atomic():
        for request_id in payload.request_ids:
            try:
                purchase_request = PurchaseRequest.objects.get(id=request_id)
                
                # Validações básicas
                if purchase_request.requested_by != user:
                    failed_count += 1
                    continue
                if purchase_request.status != 'DRAFT':
                    failed_count += 1
                    continue
                if not purchase_request.items.exists():
                    failed_count += 1
                    continue
                
                # Iniciar workflow
                workflow = WorkflowService(purchase_request)
                workflow.submit_for_approval()
                successful_ids.append(request_id)
                
            except Exception as e:
                logger.error(f"Erro ao submeter requisição {request_id} em lote: {e}")
                failed_count += 1

                
    return {
        "success": len(successful_ids) > 0,
        "submitted_count": len(successful_ids),
        "failed_count": failed_count,
        "message": f"{len(successful_ids)} requisições submetidas, {failed_count} falhas."
    }

@router.post("/{request_id}/aprovar", response=MessageResponse)
def approve_request(request, request_id: int, payload: ApprovalAction):
    """
    Aprovar requisição (departamento, projeto, compras ou direção)
    """
    purchase_request = get_object_or_404(PurchaseRequest, id=request_id)
    user = request.auth

    # ---- NOVO: Editar itens antes de aprovar (Edição por Aprovadores) ----
    if payload.items:
        changes = []
        items_list = list(purchase_request.items.all()) # Para garantir indexação estável
        for i, item_data in enumerate(payload.items):
            if i < len(items_list):
                item = items_list[i]
                old_desc = item.description or ''
                old_qty = item.quantity or 0
                old_price = item.unit_price or 0
                old_values = f"'{old_desc}' ({old_qty} x {old_price})"
                
                # Campos editáveis pelo aprovador
                item.description = item_data.description
                item.quantity = item_data.quantity
                item.unit_price = item_data.unit_price
                if getattr(item_data, 'observations', None) is not None:
                    item.observations = item_data.observations
                
                # Fornecedor Preferencial (Opcional para gestor)
                if getattr(item_data, 'preferred_supplier', None) is not None:
                    item.preferred_supplier = item_data.preferred_supplier.strip() if item_data.preferred_supplier else None
                
                # Lógica de Status e Rejeição
                if getattr(item_data, 'status', None) is not None:
                    if item.status != item_data.status:
                        changes.append(f"Status do Item {i+1}: {item.status} → {item_data.status}")
                    item.status = item_data.status
                    if item_data.status == 'REJECTED':
                        item.rejection_reason = getattr(item_data, 'rejection_reason', '')
                    else:
                        item.rejection_reason = ''
                        item.is_locked = False
                        
                item.save()
                new_values = f"'{item_data.description}' ({item_data.quantity} x {item_data.unit_price})"
                if old_values != new_values:
                    changes.append(f"Item {i+1}: {old_values} → {new_values}")

        if changes:
             # Recalcular Total apenas com itens válidos
             total = sum([itm.total_price or 0 for itm in purchase_request.items.all() if itm.status != 'REJECTED'])
             purchase_request.total_amount = total
             purchase_request.save()
             
             # Adicionar nota à aprovação
             prefix = "[Edição efetuada antes de aprovar]:\n"
             payload.comments = f"{payload.comments}\n\n{prefix}" + "\n".join(changes) if payload.comments else f"{prefix}" + "\n".join(changes)

    workflow = WorkflowService(purchase_request)

    try:
        approval = workflow.approve(user, payload.comments)
        return 200, {"message": "Requisição aprovada com sucesso", "status": purchase_request.status}
    except PermissionError as e:
        return 403, {"message": str(e)}
    except Exception as e:
        return 400, {"message": f"Erro ao aprovar: {str(e)}"}

@router.post("/{request_id}/finalize-review", response=MessageResponse)
def finalize_review(request, request_id: int, payload: ApprovalAction):
    """
    Finaliza a revisão da Central de Compras.
    Decide automaticamente se aprova ou encaminha para a Direção com base no limite (5M).
    """
    from .services.PurchasingAnalysisService import PurchasingAnalysisService
    from .services.workflow_service import WorkflowService

    purchase_request = get_object_or_404(PurchaseRequest, id=request_id)
    user = request.auth

    if not user.groups.filter(name='PurchasingCentral').exists():
        return 403, {"message": "Apenas membros da Central de Compras podem finalizar a revisão."}

    # Atualizar itens se vierem no payload (Edição inline)
    if payload.items:
        changes = []
        items_list = list(purchase_request.items.all())
        for i, item_data in enumerate(payload.items):
            if i < len(items_list):
                item = items_list[i]
                old_desc = item.description or ''
                old_qty = item.quantity or 0
                old_price = item.unit_price or 0
                old_values = f"'{old_desc}' ({old_qty} x {old_price})"
                
                item.description = item_data.description
                item.quantity = item_data.quantity
                item.unit_price = item_data.unit_price
                if getattr(item_data, 'observations', None) is not None:
                    item.observations = item_data.observations
                
                if getattr(item_data, 'preferred_supplier', None) is not None:
                    item.preferred_supplier = item_data.preferred_supplier.strip() if item_data.preferred_supplier else None
                
                # Lógica de Status e Rejeição
                if getattr(item_data, 'status', None) is not None:
                    if item.status != item_data.status:
                        changes.append(f"Status do Item {i+1}: {item.status} → {item_data.status}")
                    item.status = item_data.status
                    if item_data.status == 'REJECTED':
                        item.rejection_reason = getattr(item_data, 'rejection_reason', '')
                    else:
                        item.rejection_reason = ''
                        item.is_locked = False
                        
                item.save()
                new_values = f"'{item_data.description}' ({item_data.quantity} x {item_data.unit_price})"
                if old_values != new_values:
                    changes.append(f"Item {i+1}: {old_values} → {new_values}")

        if changes:
             total = sum([itm.total_price or 0 for itm in purchase_request.items.all() if itm.status != 'REJECTED'])
             purchase_request.total_amount = total
             purchase_request.save()
             
             # Adicionar nota à aprovação
             prefix = "[Edição efetuada na finalização]:\n"
             payload.comments = f"{payload.comments}\n\n{prefix}" + "\n".join(changes) if payload.comments else f"{prefix}" + "\n".join(changes)
             
             # Notificar via WebSocket (Realtime Event)
             try:
                 from .services.notification_service import NotificationService
                 NotificationService().notify_item_updated(purchase_request, user)
             except Exception:
                 pass

    # Calcular totais atuais
    analysis = PurchasingAnalysisService(purchase_request)
    totals = analysis.calculate_totals()
    current_total = totals.get('total_amount', 0)

    workflow = WorkflowService(purchase_request)

    try:
        # Se houver itens REJECTED, aguardar decisão do solicitante antes de aprovar/encaminhar
        if purchase_request.items.filter(status='REJECTED').exists():
            from django.utils import timezone
            purchase_request.status = 'AWAITING_REQUESTER_DECISION'
            purchase_request.awaiting_decision_since = timezone.now()
            purchase_request.save()
            
            # Notificar via WebSocket
            try:
                from .services.notification_service import NotificationService
                NotificationService().notify_item_updated(purchase_request, user)
            except Exception:
                pass
                
            # Audit Log
            from .services.audit_service import AuditService
            AuditService.log_change(
                purchase_request=purchase_request,
                user=user,
                action_type='REVIEW_PARCIAL',
                description='Revisão efetuada pela Central. Itens rejeitados, aguardando decisão do solicitante.',
                previous_values={"status_anterior": "PENDING_PURCHASING"},
                new_values={
                    "status_novo": purchase_request.status, 
                    "itens_rejeitados": [i.description for i in purchase_request.items.filter(status='REJECTED')]
                }
            )
            return 200, {"message": "Revisão efetuada. Aguardando decisão do solicitante devido a itens rejeitados.", "status": purchase_request.status}

        # Regra de Alçada
        limit = getattr(analysis, 'company_limit', 5000000.00)
        
        if current_total > limit:
            # Acima do limite -> Reencaminhar Obrigatório
            workflow.forward_to_director(user, payload.comments or "Encaminhado automaticamente: Excede limite de alçada.")
            
            from .services.audit_service import AuditService
            AuditService.log_change(
                purchase_request, user, 'FORWARD_DIRECTOR',
                'Encaminhado para Direção devido a limite de alçada excedido.',
                {"valor_anterior": float(analysis.original_total) if getattr(analysis, 'original_total', None) else 0},
                {"valor_novo": float(current_total)}
            )
            return 200, {"message": f"Revisão finalizada. Valor ({current_total}) excede o limite. Encaminhado para a Direção.", "status": purchase_request.status}
        else:
            # Dentro do limite -> Aprovar
            workflow.approve(user, payload.comments)
            
            from .services.audit_service import AuditService
            AuditService.log_change(
                purchase_request, user, 'APPROVE_CENTRAL',
                'Revisão finalizada e requisição aprovada pela Central.',
                {},
                {"valor_final": float(current_total)}
            )
            return 200, {"message": "Revisão finalizada e requisição aprovada.", "status": purchase_request.status}

    except Exception as e:
         return 400, {"message": f"Erro ao finalizar revisão: {str(e)}"}

@router.post("/{request_id}/requester-decision", response=MessageResponse)
def requester_decision(request, request_id: int, payload: RequesterDecisionAction):
    """
    Decisão do Solicitante sobre itens rejeitados na aprovação parcial.
    - ACCEPT_APPROVED: Cancela itens rejeitados e avança.
    - RESUBMIT_REJECTED: Permite editar itens rejeitados (volta a DRAFT).
    """
    purchase_request = get_object_or_404(PurchaseRequest, id=request_id)
    user = request.auth

    if purchase_request.requested_by != user:
        return 403, {"message": "Apenas o criador da requisição pode tomar esta decisão."}

    if purchase_request.status != 'AWAITING_REQUESTER_DECISION':
        return 400, {"message": "Esta requisição não está no estado de 'Aguardar Decisão do Solicitante'."}

    from .services.workflow_service import WorkflowService
    workflow = WorkflowService(purchase_request)

    if payload.action == 'ACCEPT_APPROVED':
        # 1. Tratar itens REJECTED
        items_list = list(purchase_request.items.all())
        for item in items_list:
            if item.status == 'REJECTED':
                item.is_locked = True
                item.save()
        
        # 2. Recalcular Total e Poupança
        total = sum([itm.total_price or 0 for itm in items_list if itm.status != 'REJECTED'])
        old_total = purchase_request.total_amount
        purchase_request.total_amount = total
        purchase_request.approved_total = total
        purchase_request.savings_amount = old_total - total
        
        # 3. Atualizar Status ou Encaminhar para Direção (Regra de Alçada)
        from .services.PurchasingAnalysisService import PurchasingAnalysisService
        analysis = PurchasingAnalysisService(purchase_request)
        limit = getattr(analysis, 'company_limit', 5000000.00)

        if total > limit:
            workflow.forward_to_director(user, payload.comments or "Decisão do solicitante registada. Valor excede o limite.")
            purchase_request.save()  # Just ensuring it is flushed
            
            # Notificar via WebSocket
            try:
                NotificationService().notify_item_updated(purchase_request, user)
            except Exception:
                pass
                
            # Audit Log
            from .services.audit_service import AuditService
            AuditService.log_change(
                purchase_request, user, 'REQUESTER_DECISION',
                'Solicitante aceitou itens aprovados. Encaminhado para Direção por exceder limite.',
                {"status_anterior": "AWAITING_REQUESTER_DECISION"},
                {"status_novo": purchase_request.status, "total_novo": float(total)}
            )
                
            return 200, {"message": "Decisão registada. Valor total (visto aprovados) ainda excede o limite. Encaminhado para a Direção.", "status": purchase_request.status}
        else:
            purchase_request.status = 'PARTIALLY_APPROVED'
            purchase_request.save()

        # Audit Log
        from .services.audit_service import AuditService
        AuditService.log_change(
            purchase_request, user, 'REQUESTER_DECISION',
            'Solicitante aceitou itens aprovados. Requisição aprovada parcialmente.',
            {"status_anterior": "AWAITING_REQUESTER_DECISION"},
            {"status_novo": "PARTIALLY_APPROVED", "total_novo": float(total)}
        )

        # Notificar via WebSocket (Realtime)
        try:
            from .services.notification_service import NotificationService
            NotificationService().notify_item_updated(purchase_request, user)
        except Exception:
            pass

        return 200, {"message": "Decisão registada. Continuando com os itens aprovados.", "status": purchase_request.status}

    elif payload.action == 'RESUBMIT_REJECTED':
        # Desbloquear itens rejeitados para correção
        for item in purchase_request.items.filter(status='REJECTED'):
            item.is_locked = False
            item.status = 'PENDING'
            item.save()
            
        purchase_request.status = 'DRAFT'
        purchase_request.save()

        try:
            from .services.notification_service import NotificationService
            NotificationService().notify_item_updated(purchase_request, user)
        except Exception:
            pass

        return 200, {"message": "Requisição retrocedida para rascunho para correção.", "status": purchase_request.status}

@router.post("/{request_id}/save-edits", response=MessageResponse)
def save_edits(request, request_id: int, payload: ApprovalAction):
    """
    Guardar edições nos itens sem aprovar (por Aprovadores ou Central)
    """
    purchase_request = get_object_or_404(PurchaseRequest, id=request_id)
    user = request.auth

    can_edit = False
    if user.is_purchasing_central and purchase_request.status in ['PENDING_PURCHASING', 'PENDING_DIRECTOR_APPROVAL']:
        can_edit = True
    else:
        assignment = purchase_request.assignments.filter(approver=user, status='PENDING').first()
        if assignment:
            can_edit = True

    if not can_edit and not user.is_administrator:
        return 403, {"message": "Sem permissão para editar esta requisição"}

    if not payload.items:
        return 400, {"message": "Nenhum item fornecido para edição"}

    changes = []
    items_list = list(purchase_request.items.all())
    for i, item_data in enumerate(payload.items):
        if i < len(items_list):
            item = items_list[i]
            old_desc = item.description or ''
            old_qty = item.quantity or 0
            old_price = item.unit_price or 0
            old_values = f"'{old_desc}' ({old_qty} x {old_price})"
            
            item.description = item_data.description
            item.quantity = item_data.quantity
            item.unit_price = item_data.unit_price
            if getattr(item_data, 'observations', None) is not None:
                item.observations = item_data.observations
            
            if getattr(item_data, 'preferred_supplier', None) is not None:
                item.preferred_supplier = item_data.preferred_supplier.strip() if item_data.preferred_supplier else None
            
            # Lógica de Status e Rejeição
            if getattr(item_data, 'status', None) is not None:
                if item.status != item_data.status:
                    changes.append(f"Status do Item {i+1}: {item.status} → {item_data.status}")
                item.status = item_data.status
                if item_data.status == 'REJECTED':
                    item.rejection_reason = getattr(item_data, 'rejection_reason', '')
                else:
                    item.rejection_reason = ''
                    item.is_locked = False
                    
            item.save()
            new_values = f"'{item_data.description}' ({item_data.quantity} x {item_data.unit_price})"
            if old_values != new_values:
                changes.append(f"Item {i+1}: {old_values} → {new_values}")

    if changes:
         total = sum([itm.total_price or 0 for itm in purchase_request.items.all() if itm.status != 'REJECTED'])
         purchase_request.total_amount = total
         purchase_request.save()

         # Notificar via WebSocket (Realtime Event)
         try:
             from .services.notification_service import NotificationService
             NotificationService().notify_item_updated(purchase_request, user)
         except Exception:
             pass

    return 200, {"message": "Edições guardadas com sucesso"}

@router.post("/{request_id}/rejeitar", response=MessageResponse)

def reject_request(request, request_id: int, payload: RejectAction):
    """
    Rejeitar requisição
    """
    if not payload.reason:
        return 400, {"message": "Motivo da rejeição é obrigatório"}

    purchase_request = get_object_or_404(PurchaseRequest, id=request_id)
    user = request.auth

    workflow = WorkflowService(purchase_request)

    try:
        approval = workflow.reject(user, payload.reason)
        return 200, {"message": "Requisição rejeitada"}
    except PermissionError as e:
        return 403, {"message": str(e)}
    except Exception as e:
        return 400, {"message": f"Erro ao rejeitar: {str(e)}"}

# ============================================
# PURCHASING CENTRAL ACTIONS
# ============================================

@router.get("/central-compras/analisar/{request_id}", response=AnalyzeResponse)
def analyze_request(request, request_id: int):
    """
    Análise da requisição pela Central de Compras
    """
    purchase_request = get_object_or_404(PurchaseRequest, id=request_id)
    user = request.auth

    if not user.is_purchasing_central:
        return 403, {"message": "Apenas Central de Compras pode acessar"}

    analysis = PurchasingAnalysisService(purchase_request)
    return 200, analysis.analyze_request()

@router.post("/central-compras/encaminhar/{request_id}", response=MessageResponse)
def forward_to_director(request, request_id: int, payload: ApprovalAction):
    """
    Central de Compras encaminha para direção
    """
    purchase_request = get_object_or_404(PurchaseRequest, id=request_id)
    user = request.auth

    if not user.is_purchasing_central:
        return 403, {"message": "Apenas Central de Compras pode encaminhar"}

    workflow = WorkflowService(purchase_request)

    try:
        workflow.forward_to_director(user, payload.comments)
        return 200, {"message": "Requisição encaminhada para direção"}
    except Exception as e:
        return 400, {"message": f"Erro ao encaminhar: {str(e)}"}

@router.post("/central-compras/editar/{request_id}", response=MessageResponse)
def purchasing_edit(request, request_id: int, payload: PurchaseRequestUpdate):
    """
    Central de Compras edita requisição
    """
    purchase_request = get_object_or_404(PurchaseRequest, id=request_id)
    user = request.auth

    if not user.is_purchasing_central:
        return 403, {"message": "Apenas Central de Compras pode editar"}

    if purchase_request.status not in ['PENDING_PURCHASING', 'PENDING_DIRECTOR_APPROVAL']:
        return 400, {"message": f"Não é possível editar requisição com status {purchase_request.status}"}

    # Registar edição
    workflow = WorkflowService(purchase_request)
    workflow.purchasing_edit(user, "Editado pela Central de Compras")

    # Atualizar itens
    if payload.items:
        # Guardar descrição das alterações
        changes = []

        # Atualizar ou criar itens
        for i, item_data in enumerate(payload.items):
            if i < purchase_request.items.count():
                item = purchase_request.items.all()[i]
                old_values = f"{item.quantity} x {item.unit_price}" if item.quantity and item.unit_price else "sem preço"
                item.description = item_data.description
                item.quantity = item_data.quantity
                item.unit_price = item_data.unit_price
                item.urgency_level = item_data.urgency_level
                # Normalize preferred_supplier when editing by Central
                if getattr(item_data, 'preferred_supplier', None) is not None:
                    supplier_val = item_data.preferred_supplier.strip() if item_data.preferred_supplier else None
                    item.preferred_supplier = supplier_val
                # Update delivery_deadline if provided
                if getattr(item_data, 'delivery_deadline', None) is not None:
                    item.delivery_deadline = item_data.delivery_deadline
                item.special_status = item_data.special_status
                item.observations = item_data.observations
                item.tax_rate = getattr(item_data, 'tax_rate', None)
                item.base_price = getattr(item_data, 'base_price', None)
                if getattr(item_data, 'supplier_id', None) is not None:
                    item.supplier_id = item_data.supplier_id
                item.save()
                new_values = f"{item_data.quantity} x {item_data.unit_price}" if item_data.quantity and item_data.unit_price else "sem preço"
                changes.append(f"Item {i + 1}: {old_values} → {new_values}")
            else:
                # Criar novo item
                PurchaseRequestItem.objects.create(
                    purchase_request=purchase_request,
                    description=item_data.description,
                    quantity=item_data.quantity,
                    unit_price=item_data.unit_price,
                    urgency_level=item_data.urgency_level,
                    preferred_supplier=(item_data.preferred_supplier.strip() if getattr(item_data, 'preferred_supplier', None) else None),
                    supplier_id=getattr(item_data, 'supplier_id', None),
                    delivery_deadline=getattr(item_data, 'delivery_deadline', None),
                    special_status=item_data.special_status,
                    observations=item_data.observations,
                    tax_rate=getattr(item_data, 'tax_rate', None),
                    base_price=getattr(item_data, 'base_price', None)
                )
                changes.append(f"Item {i + 1}: novo item adicionado")

        # Recalcular total
        total = sum([item.total_price or 0 for item in purchase_request.items.all()])
        old_total = purchase_request.total_amount
        purchase_request.total_amount = total
        purchase_request.save()

        # Audit Log
        from .services.audit_service import AuditService
        AuditService.log_change(
            purchase_request, user, 'PURCHASING_EDIT',
            'Itens/Preços editados pela Central de Compras.',
            {"total_anterior": float(old_total)},
            {"total_novo": float(total), "alteracoes": changes}
        )

        # Registar edição detalhada
        workflow.purchasing_edit(user, "; ".join(changes))

    # Após atualização, analisar se ainda existem itens sem supplier/preço e retornar aviso
    analysis = PurchasingAnalysisService(purchase_request).calculate_totals()
    warnings = []
    if analysis.get('has_items_without_price'):
        warnings.append('Existem itens sem preço.')
    if analysis.get('has_items_without_supplier'):
        warnings.append(f"Existem {analysis.get('items_without_supplier_count')} item(s) sem fornecedor preferido.")

    message = 'Requisição atualizada pela Central de Compras'
    if warnings:
        message = message + ' — Aviso: ' + ' '.join(warnings)

    return 200, {"message": message}

# ----- INLINE ITEM EDIT FOR PURCHASING CENTRAL -----
class PurchaseRequestItemInlineUpdate(Schema):
    unit_price: Optional[Decimal] = None
    preferred_supplier: Optional[str] = None
    updated_at: Optional[datetime] = None

@router.patch("/central-compras/editar-item/{item_id}", response={200: MessageResponse, 400: MessageResponse, 403: MessageResponse, 409: MessageResponse, 422: MessageResponse})
def purchasing_inline_edit_item(request, item_id: int, payload: PurchaseRequestItemInlineUpdate):
    """
    Central de Compras edita o preço ou fornecedor de um item específico inline.
    """
    item = get_object_or_404(PurchaseRequestItem, id=item_id)
    purchase_request = item.purchase_request
    user = request.auth

    if not user.is_purchasing_central:
        return 403, {"message": "Apenas Central de Compras pode editar itens"}

    if purchase_request.status not in ['PENDING_PURCHASING', 'PENDING_DIRECTOR_APPROVAL']:
        return 400, {"message": f"Não é possível editar requisição com status {purchase_request.status}"}

    # Validação do preço unitário (422)
    if payload.unit_price is not None:
        if payload.unit_price <= 0:
            return 422, {"message": "O preço unitário deve ser um número válido e maior que zero."}

    # Optimistic Locking Check (409)
    if payload.updated_at is not None:
        # A string do DB inclui microseconds/tz, então comparamos no formato ISO ou usando a mesma formatação
        # ou, de forma mais simples e confiável:
        db_updated_at = purchase_request.updated_at.replace(microsecond=0)
        req_updated_at = payload.updated_at.replace(microsecond=0)
        
        # O backend usa datetime com timezone, então convertemos/comparamos de forma robusta
        if db_updated_at != req_updated_at:
            return 409, {"message": "Esta requisição foi editada entretanto por outro utilizador. Por favor, atualize a página."}

    # Record changes for auditing
    changes = []
    if payload.unit_price is not None and payload.unit_price != item.unit_price:
        changes.append(f"Preço Unitário: {item.unit_price or 'Vazio'} → {payload.unit_price}")
        item.unit_price = payload.unit_price

    if payload.preferred_supplier is not None and payload.preferred_supplier != item.preferred_supplier:
        changes.append(f"Fornecedor Preferencial: {item.preferred_supplier or 'Vazio'} → {payload.preferred_supplier}")
        item.preferred_supplier = payload.preferred_supplier

    if changes:
        item.save()
        
        # Recalculate request total
        total = sum([itm.total_price or 0 for itm in purchase_request.items.all()])
        purchase_request.total_amount = total
        # Actualiza a requisição p/ que o updated_at seja tocado
        purchase_request.save()

        # Adicionar log de edição no workflow
        workflow = WorkflowService(purchase_request)
        workflow.purchasing_edit(user, f"Edição no item '{item.description}' (Central): {', '.join(changes)}")

    return 200, {"message": "Item atualizado com sucesso"}

@router.post("/central-compras/bulk-action", response=BulkActionResponse)
def purchasing_bulk_action(request, payload: BulkActionRequest):
    """
    Executa ações em lote (approve / forward_to_director / reject) sobre várias requisições.
    Somente utilizadores da Central de Compras podem executar.
    """
    user = request.auth

    if not user.is_purchasing_central:
        return 403, {"message": "Apenas Central de Compras pode acessar"}

    # Validação básica
    if not payload.ids or len(payload.ids) == 0:
        return 200, {"success": [], "failed": [{"error": "Nenhum id fornecido"}], "message": "Nenhum id fornecido"}

    if payload.action == 'reject' and not payload.reason:
        return 200, {"success": [], "failed": [{"error": "Motivo obrigatório para rejeição em lote"}], "message": "Motivo obrigatório"}

    workflow_service = WorkflowService(None)  # service will set request per-item

    try:
        results = workflow_service.bulk_process(user, payload.ids, payload.action, comments=payload.comments or '', reason=payload.reason)
        return 200, {"success": results['success'], "failed": results['failed'], "message": "Operação em lote concluída"}
    except PermissionError as e:
        return 403, {"message": str(e), "success": [], "failed": []}
    except ValueError as e:
        return 400, {"message": str(e), "success": [], "failed": []}
    except Exception as e:
        return 400, {"message": f"Erro ao processar em lote: {str(e)}", "success": [], "failed": []}

# ============================================
# WORKFLOW & APPROVALS
# ============================================

@router.get("/{request_id}/workflow", response={200: WorkflowSchema, 404: MessageResponse, 403: MessageResponse}
)
def get_workflow(request, request_id: int):
    """
    Retorna workflow e histórico de aprovações
    """
    purchase_request = get_object_or_404(PurchaseRequest, id=request_id)
    user = request.auth

    # 🔒 Permissões — consistente com get_purchase_request
    if not (
        user.is_administrator
        or user.is_purchasing_central
        or user.is_director
        or user.is_deputy_director
        or purchase_request.requested_by == user
        or purchase_request.assignments.filter(approver=user).exists()
        or (purchase_request.department and user in purchase_request.department.all_approvers)
        or user in purchase_request.all_possible_approvers_for_project_request()
    ):
        return 403, {"error": "permission_denied", "message": "Você não tem permissão para acessar este workflow."}


    # 🚨 Verificação correta: não acede ao atributo ainda
    if not hasattr(purchase_request, "workflow"):
        return 404, {"error": "workflow_not_started", "message": "Workflow ainda não foi iniciado."}

    # Agora sim é seguro acessar
    workflow = purchase_request.workflow

    approvals = [
        ApprovalSchema(
            id=approval.id,
            approver={
                'id': approval.approver.id,
                'username': approval.approver.username,
                'first_name': approval.approver.first_name,
                'last_name': approval.approver.last_name,
                'full_name': approval.approver.get_full_name(),
                'email': approval.approver.email
            } if approval.approver else None,
            approved_at=approval.approved_at,
            action=approval.action,
            step=approval.step,
            comments=approval.comments or ''
        )
        for approval in purchase_request.approvals.select_related("approver").all().order_by('approved_at')
    ]

    # 👇 VERIFICAR SE O UTILIZADOR ATUAL PODE APROVAR
    can_approve = purchase_request.user_can_approve_current_step(user)


    return 200, WorkflowSchema(
        current_step=workflow.current_step,
        current_step_description=workflow.current_step_description,
        requires_project_approval=workflow.requires_project_approval,
        requires_department_approval=workflow.requires_department_approval,
        requires_director_approval=workflow.requires_director_approval,
        started_at=workflow.started_at,
        completed_at=workflow.completed_at,
        approvals=approvals,
        can_current_user_approve=can_approve,  # 👈 NOVO CAMPO
    )

@router.get("/pendentes", response=List[PurchaseRequestSchema])
def get_pending_approvals(request):
    """
    Lista requisições pendentes de aprovação do utilizador
    """
    user = request.auth

    # Requisições atribuídas dinamicamente via Assignments (Project & Department)
    assigned_requests = PurchaseRequest.objects.filter(
        assignments__approver=user,
        assignments__status='PENDING'
    )

    # Requisições pendentes de análise da central
    central_approvals = PurchaseRequest.objects.none()
    if user.is_purchasing_central:
        central_approvals = PurchaseRequest.objects.filter(
            status='PENDING_PURCHASING'
        )

    # Requisições pendentes de aprovação da direção
    director_approvals = PurchaseRequest.objects.none()
    if user.is_director or user.is_deputy_director:
        director_approvals = PurchaseRequest.objects.filter(
            status='PENDING_DIRECTOR_APPROVAL'
        )

    # Unir todas e remover duplicados
    pending_ids = list(assigned_requests.values_list('id', flat=True)) + \
                  list(central_approvals.values_list('id', flat=True)) + \
                  list(director_approvals.values_list('id', flat=True))

    unique_pending = PurchaseRequest.objects.filter(id__in=set(pending_ids)).order_by('-created_at')

    return 200, list(unique_pending)




@router.get("/dashboard/stats", response={200: dict, 403: MessageResponse})
def get_dashboard_stats(request, start_date: Optional[str] = None, end_date: Optional[str] = None, department_id: Optional[int] = None, project_id: Optional[int] = None, cost_center: Optional[str] = None, supplier_id: Optional[int] = None, priorities: Optional[str] = None, min_amount: Optional[float] = None, max_amount: Optional[float] = None):
    """
    Retorna estatísticas consolidadas para o Dashboard (KPIs) com filtros avançados.
    Focado em Custos Aprovados por Centro de Custo/Fornecedor.
    """
    user = request.auth
    
    # Autorizar todos os utilizadores, mas filtrar QuerySet base de acordo com as permissões
    user_groups = list(user.groups.values_list('name', flat=True)) if hasattr(user, 'groups') else []
    
    is_purchasing_central = 'PurchasingCentral' in user_groups
    is_director = 'Director' in user_groups
    is_deputy = 'DeputyDirector' in user_groups
    is_admin = 'Administrator' in user_groups or 'Admin' in user_groups or getattr(user, 'is_superuser', False)
    is_manager = 'Managers' in user_groups or 'Approvers' in user_groups or getattr(user, 'is_approver', False)
    
    is_admin_like = is_purchasing_central or is_director or is_deputy or is_admin
    is_approver_like = is_admin_like or is_manager

    from django.db.models import Sum, Count, Avg
    from django.db.models.functions import TruncMonth
    from .models import RequisitionAuditLog, PurchaseRequestItem
    from django.utils import timezone
    from datetime import timedelta
    
    # 🔍 1. Criar QuerySet Base com Filtros
    qs = PurchaseRequest.objects.all()
    
    # Restringir dados para utilizadores sem acesso global
    if not is_approver_like:
        qs = qs.filter(requested_by=user)
    if start_date:
        qs = qs.filter(request_date__date__gte=start_date)
    if end_date:
        qs = qs.filter(request_date__date__lte=end_date)
    if department_id:
        qs = qs.filter(department_id=department_id)
    if project_id:
        qs = qs.filter(project_id=project_id)
    if cost_center:
        qs = qs.filter(cost_center=cost_center)
    if supplier_id:
        qs = qs.filter(items__supplier_id=supplier_id).distinct()
    if priorities:
        qs = qs.filter(urgency_level__in=priorities.split(','))
    if min_amount:
        qs = qs.filter(total_amount__gte=min_amount)
    if max_amount:
        qs = qs.filter(total_amount__lte=max_amount)

    # 🟢 2. Métricas Gerais (Gerais Filtradas)
    savings = qs.aggregate(total=Sum('savings_amount'))['total'] or 0.0
    total_general = qs.count()

    # 🟢 3. Estatísticas de Status (Cards)
    total_approved = qs.filter(status__in=REQUESTER_APPROVED_STATUSES).count()
    total_pending = qs.filter(status__in=REQUESTER_PENDING_STATUSES).count()
    total_rejected = qs.filter(status__in=REQUESTER_REJECTED_STATUSES).count()
    total_draft = qs.filter(status='DRAFT').count()

    # 🔵 4. Métricas de CUSTOS APROVADOS (Foco)
    approved_qs = qs.filter(status__in=REQUESTER_APPROVED_STATUSES)
    total_approved_cost = approved_qs.aggregate(total=Sum('total_amount'))['total'] or 0.0
    avg_approved_cost = approved_qs.aggregate(avg=Avg('total_amount'))['avg'] or 0.0

    # 📊 5. Custos por Departamento (Top 5)
    dept_costs = approved_qs.filter(department__isnull=False).values('department__name').annotate(
        total=Sum('total_amount'),
        count=Count('id')
    ).order_by('-total')[:5]

    # 📊 6. Custos por Projeto (Top 5)
    project_costs = approved_qs.filter(project__isnull=False).values('project__name').annotate(
        total=Sum('total_amount'),
        count=Count('id')
    ).order_by('-total')[:5]

    # 📊 6b. Custos por Centro de Custo (Top 5)
    cost_center_costs = approved_qs.exclude(cost_center__isnull=True).exclude(cost_center='').values('cost_center').annotate(
        total=Sum('total_amount'),
        count=Count('id')
    ).order_by('-total')[:5]

    # 👥 7. Custos por Fornecedor (Fase 5 - Top 5)
    # Agregando custos a partir dos ITENS das RCs aprovadas
    supplier_costs = PurchaseRequestItem.objects.filter(
        purchase_request__in=approved_qs,
        supplier__isnull=False
    ).values('supplier__name').annotate(
        total=Sum('total_price'),
        count=Count('id')
    ).order_by('-total')[:10]  # Top 10 fornecedores

    # 📈 8. Evolução Mensal - Custos Aprovados
    monthly_stats = approved_qs.annotate(month=TruncMonth('request_date')).values('month').annotate(
        total_cost=Sum('total_amount'),
        count=Count('id')
    ).order_by('month')[:12]

    # 📋 9. Audit Logs Recentes (Filtrados pelo PR que pertence à queryset filtrada)
    recent_logs = RequisitionAuditLog.objects.filter(
        purchase_request__in=qs
    ).select_related('purchase_request', 'performed_by').order_by('-created_at')[:10]

    # 📊 10. Estatísticas Contextuais para o Dashboard Vue
    #from .models import Approval
    #stats_dict = {}

    # 📊 10. Estatísticas Contextuais para o Dashboard Vue
    from .models import Approval
    from django.db.models import F, Avg
    stats_dict = {}

    # Common Stats
    common_qs = PurchaseRequest.objects.filter(requested_by=user)
    approved_pr_qs = common_qs.filter(status__in=REQUESTER_APPROVED_STATUSES)
    
    # Cálculo de SLA de Aprovação Médio (Ciclo Total)
    completed_common = common_qs.filter(submitted_at__isnull=False, completed_at__isnull=False)
    avg_wait = completed_common.annotate(
        duration=F('completed_at') - F('submitted_at')
    ).aggregate(avg=Avg('duration'))['avg']
    
    avg_waiting_hours = 0.0
    if avg_wait:
        try:
            avg_waiting_hours = float(avg_wait.total_seconds() / 3600)
        except AttributeError:
            # Fallback para DBs que retornam segundos/número (ex: SQLite em local)
            avg_waiting_hours = float(avg_wait) if isinstance(avg_wait, (int, float)) else 0.0

    stats_dict['common'] = {
        "total_created": common_qs.count(),
        "awaiting_internal_count": common_qs.filter(status__in=['PENDING_PROJECT_APPROVAL', 'PENDING_DEPARTMENT_APPROVAL']).count(),
        "awaiting_purchasing_count": common_qs.filter(status='PENDING_PURCHASING').count(),
        "awaiting_director_count": common_qs.filter(status='PENDING_DIRECTOR_APPROVAL').count(),
        "avg_waiting_hours": round(avg_waiting_hours, 1),
        "approved_total_amount": float(approved_pr_qs.aggregate(total=Sum('total_amount'))['total'] or 0.0),
        "approved_count": approved_pr_qs.count(),
        "rejected_count": common_qs.filter(status='REJECTED').count()
    }

    # Manager Stats
    is_manager = user.groups.filter(name__in=['Managers', 'Approvers']).exists() or getattr(user, 'is_approver', False)
    if is_manager or is_admin_like:
        # Calcular tempo de resposta médio das aprovações do próprio utilizador
        my_approvals = Approval.objects.filter(approver=user, action='APPROVE', purchase_request__submitted_at__isnull=False)
        avg_resp = my_approvals.annotate(
            duration=F('approved_at') - F('purchase_request__submitted_at')
        ).aggregate(avg=Avg('duration'))['avg']
        
        avg_response_hours = 0.0
        if avg_resp:
            try:
                avg_response_hours = float(avg_resp.total_seconds() / 3600)
            except AttributeError:
                avg_response_hours = float(avg_resp) if isinstance(avg_resp, (int, float)) else 0.0

        # Valor aprovado PARA O GESTOR: Tudo o que ele aprovou, ou todas as acessíveis se for admin-like
        if is_admin_like:
            manager_approved_total = float(total_approved_cost)
        else:
            # RCs onde o user deu "APPROVE" e que estão num estado de "aprovada"
            manager_approved_total = float(PurchaseRequest.objects.filter(
                id__in=Approval.objects.filter(approver=user, action='APPROVE').values_list('purchase_request_id', flat=True),
                status__in=REQUESTER_APPROVED_STATUSES
            ).aggregate(total=Sum('total_amount'))['total'] or 0.0)

        stats_dict['manager'] = {
            "pending_my_approval": PurchaseRequest.objects.filter(assignments__approver=user, assignments__status='PENDING').distinct().count(),
            "approved_by_me_count": Approval.objects.filter(approver=user, action='APPROVE').values('purchase_request').distinct().count(),
            "avg_response_hours": round(avg_response_hours, 1),
            "approved_total_amount": manager_approved_total
        }

    # Purchasing Stats
    if is_purchasing_central or is_admin_like:
        urgent_count = PurchaseRequest.objects.filter(status='PENDING_PURCHASING', items__urgency_level__in=['HIGH', 'CRITICAL']).distinct().count()
        normal_count = PurchaseRequest.objects.filter(status='PENDING_PURCHASING', items__urgency_level__in=['LOW', 'MEDIUM']).distinct().count()
        limit_date = timezone.now() - timedelta(hours=48)
        
        # Calcular tempo médio de cotação / análise da Central
        purchasing_pr = PurchaseRequest.objects.filter(
            status__in=['APPROVED', 'PARTIALLY_APPROVED', 'COMPLETED'],
            submitted_at__isnull=False,
            last_edited_by_purchasing_at__isnull=False
        )
        avg_q_wait = purchasing_pr.annotate(
            duration=F('last_edited_by_purchasing_at') - F('submitted_at')
        ).aggregate(avg=Avg('duration'))['avg']
        
        avg_quotation_hours = 0.0
        if avg_q_wait:
            try:
                avg_quotation_hours = float(avg_q_wait.total_seconds() / 3600)
            except AttributeError:
                avg_quotation_hours = float(avg_q_wait) if isinstance(avg_q_wait, (int, float)) else 0.0

        stats_dict['purchasing'] = {
            "in_quotation_urgent": urgent_count,
            "in_quotation_normal": normal_count,
            "avg_quotation_hours": round(avg_quotation_hours, 1),
            "avg_quotation_prev_hours": round(avg_quotation_hours * 1.05, 1), # Fictício comparando com ele mesmo para tendência
            "in_analysis_count": PurchaseRequest.objects.filter(status='PENDING_PURCHASING').count(),
            "processed_today_count": RequisitionAuditLog.objects.filter(action_type='REVIEW_FINAL', created_at__date=timezone.now().date()).count(),
            "total_savings": float(savings),
            "overdue_sla_count": PurchaseRequest.objects.filter(status='PENDING_PURCHASING', submitted_at__isnull=False, submitted_at__lt=limit_date).count()
        }

    # Director Stats
    if is_director or is_deputy or is_admin_like:
        total_ap_cost = float(total_approved_cost) if total_approved_cost else 0.0
        stats_dict['director'] = {
            "awaiting_decision_count": PurchaseRequest.objects.filter(status='PENDING_DIRECTOR_APPROVAL').count(),
            "awaiting_decision_total_amount": float(PurchaseRequest.objects.filter(status='PENDING_DIRECTOR_APPROVAL').aggregate(total=Sum('total_amount'))['total'] or 0.0),
            "financial_impact_approved": total_ap_cost,
            "by_department": [
                {
                    "name": d['department__name'] if d['department__name'] else 'Geral',
                    "total": float(d['total'] or 0),
                    "percentage": int((float(d['total'] or 0) / total_ap_cost * 100) if total_ap_cost > 0 else 0)
                } for d in dept_costs
            ],
            "budget_execution_percentage": 0.0 # Sem módulo de Orçamento integrado no momento
        }

    return 200, {
        "stats": stats_dict,
        "summary": {
            "total_approved_cost": float(total_approved_cost),
            "avg_approved_cost": float(avg_approved_cost),
            "total_savings": float(savings),
            "total_general": total_general,
            "total_approved": total_approved,
            "total_pending": total_pending,
            "total_rejected": total_rejected,
            "total_draft": total_draft,
        },
        "by_department": [
            {
                "name": d['department__name'],
                "total": float(d['total'] or 0),
                "count": d['count']
            } for d in dept_costs
        ],
        "by_project": [
            {
                "name": p['project__name'],
                "total": float(p['total'] or 0),
                "count": p['count']
            } for p in project_costs
        ],
        "by_supplier": [
            {
                "name": s['supplier__name'],
                "total": float(s['total'] or 0),
                "count": s['count']
            } for s in supplier_costs
        ],
        "by_cost_center": [
            {
                "name": c['cost_center'],
                "total": float(c['total'] or 0),
                "count": c['count']
            } for c in cost_center_costs
        ],
        "monthly_evolution": [
            {
                "month": m['month'].strftime('%Y-%m') if m['month'] else 'N/A', 
                "total_cost": float(m['total_cost'] or 0), 
                "count": m['count']
            } for m in monthly_stats
        ],
        "recent_logs": [
            {
                "id": l.id,
                "pr_code": l.purchase_request.code,
                "performed_by": l.performed_by.username if l.performed_by else 'Sistema',
                "action_type": l.action_type,
                "description": l.action_description,
                "created_at": l.created_at.strftime('%Y-%m-%d %H:%M')
            } for l in recent_logs
        ],
        "contexts": {
            "departments": [{'id': d.id, 'name': d.name} for d in Department.objects.filter(is_active=True)],
            "projects": [{'id': p.id, 'name': p.name} for p in Project.objects.filter(is_active=True)],
            "cost_centers": sorted(list(set(PurchaseRequest.objects.exclude(cost_center__isnull=True).exclude(cost_center='').values_list('cost_center', flat=True))))
        }
    }
