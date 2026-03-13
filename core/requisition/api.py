# api/endpoints.py
from ninja import Router, File
from ninja.files import UploadedFile
from ninja.pagination import paginate, PageNumberPagination
from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.utils import timezone
import logging
import os

logger = logging.getLogger(__name__)
from rest_framework.decorators import authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication

from django.core.signing import TimestampSigner, BadSignature, SignatureExpired
import mimetypes
from django.http import FileResponse

from .models import PurchaseRequest, PurchaseRequestItem, Attachment
from .schemas import *
from core.requisition.schemas import BulkActionRequest, BulkActionResponse

from .services.PurchasingAnalysisService import PurchasingAnalysisService
from .services.workflow_service import WorkflowService
from ..erp.models import Department
from ..project.models import Project
from .schemas import AnalyzeResponse

router = Router(tags=["Requisition"])

# ============================================
# DEBUG: Listar endpoints registrados (remover em produção)
# ============================================
print("\n" + "="*50)
print("ENDPOINTS REGISTRADOS NO ROUTER DE REQUISIÇÃO")
print("="*50)


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
            status__in=['COMPLETED', 'REJECTED', 'CANCELLED']
        ).distinct()

    if overdue:
        today = timezone.now().date()
        queryset = queryset.filter(
            required_date__lt=today
        ).exclude(
            status__in=['COMPLETED', 'REJECTED', 'CANCELLED']
        )
        
    return {"count": queryset.count()}


@router.get("/counts-by-status", response=dict)
def get_counts_by_status(request):
    """
    Retorna contagem de requisições do PRÓPRIO utilizador agrupadas por status (para banners).
    Os banners de aprovadas/rejeitadas são para o solicitante saber o estado das SUAS requisições.
    """
    user = request.auth

    # Contar apenas as requisições submetidas pelo próprio utilizador
    my_requests = PurchaseRequest.objects.filter(requested_by=user)

    return {
        "all": my_requests.count(),
        "pending": my_requests.filter(status__startswith='PENDING').count(),
        "approved": my_requests.filter(status='APPROVED').count(),
        "rejected": my_requests.filter(status='REJECTED').count(),
        "draft": my_requests.filter(status='DRAFT').count(),
    }



@router.get("/list", response=List[PurchaseRequestSchema])
@paginate(PageNumberPagination, page_size=20)
def list_purchase_requests(request, status: str = None, context: str = None, urgency: str = None, 
                           search: str = None, tab: str = None, assigned_to_me: bool = False, 
                           assignment_status: str = None,
                           edited_by_purchasing: bool = False, is_urgent: bool = False, overdue: bool = False,
                           reference_month: str = None, cost_center: str = None):
    """
    Listar requisições (com filtros)
    """
    user = request.auth
    queryset = PurchaseRequest.objects.all()

    # Filtrar por permissões base
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
            # Pessoas normais veem as próprias requisições OU as que lhe foram atribuídas (Assignments)
            queryset = queryset.filter(
                Q(requested_by=user) | 
                Q(assignments__approver=user)
            ).distinct()

    # Lógica de ABAS (tab)
    if tab:
        if tab == 'draft':
            queryset = queryset.filter(status='DRAFT')
        elif tab == 'pending':
            if user.is_purchasing_central:
                # Para central, se enviou para direção não é pendente para eles
                queryset = queryset.filter(status='PENDING_PURCHASING')
            elif user.is_director or user.is_deputy_director:
                queryset = queryset.filter(status='PENDING_DIRECTOR_APPROVAL')
            else:
                queryset = queryset.filter(status__startswith='PENDING')
        elif tab == 'approved':
            if user.is_purchasing_central:
                # O que já mandaram para direção, consideram aprovado por eles, e o que a direção aprovou
                queryset = queryset.filter(status__in=['PENDING_DIRECTOR_APPROVAL', 'APPROVED'])
            else:
                queryset = queryset.filter(status='APPROVED')
        elif tab == 'rejected':
            queryset = queryset.filter(status='REJECTED')

    # Filtro "Minhas aprovações" (assigned_to_me ou assignment_status específico)
    if assigned_to_me or assignment_status:
        if user.is_purchasing_central:
            # Para Central, filters simples por status da RC costumam bastar,
            # mas vamos honrar o assignment_status se vier.
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
            # Filtragem exata e eficiente usando a nova tabela de Assignments
            status_to_filter = assignment_status if assignment_status else 'PENDING'
            queryset = queryset.filter(
                assignments__approver=user, 
                assignments__status=status_to_filter
            ).distinct()

    # Filtro Editadas
    # Filtro Editadas
    if edited_by_purchasing:
        queryset = queryset.filter(last_edited_by_purchasing_at__isnull=False)

    # Filtros Rápidos (Urgentes e Atrasadas)
    if is_urgent:
        from datetime import timedelta
        limit_date = timezone.now().date() + timedelta(days=2)
        queryset = queryset.filter(
            Q(items__urgency_level__in=['HIGH', 'CRITICAL']) |
            Q(required_date__isnull=False, required_date__lte=limit_date)
        ).exclude(
            status__in=['COMPLETED', 'REJECTED', 'CANCELLED']
        ).distinct()
        
    if overdue:
        # A data necessária já passou e não está completo
        today = timezone.now().date()
        queryset = queryset.filter(
            required_date__lt=today
        ).exclude(
            status__in=['COMPLETED', 'REJECTED', 'CANCELLED']
        )

    # Filtros exatos
    if status:
        queryset = queryset.filter(status=status)
    if context:
        queryset = queryset.filter(context_type=context)
    if reference_month:
        queryset = queryset.filter(reference_month=reference_month)
    if cost_center:
        queryset = queryset.filter(cost_center__icontains=cost_center)
    if urgency:
        # Filtro de urgência antigo (mantido para compatibilidade, se necessário)
        queryset = queryset.filter(items__urgency_level=urgency).distinct()

    # Filtro de Busca Livre
    if search:
        # Extrai número do código (suporta "RC-000001", "RC-TI-2026-000001" ou apenas "1")
        search_id = None
        search_upper = search.strip().upper()
        
        # Tenta extrair a parte numérica final
        if '-' in search_upper:
            parts = search_upper.split('-')
            last_part = parts[-1].lstrip('0') or '0'
            try:
                search_id = int(last_part)
            except ValueError:
                pass
        else:
            # Caso o utilizador digite apenas o número ou "RC0001"
            search_clean = search_upper.lstrip('RC').lstrip('0') or '0'
            try:
                search_id = int(search_clean)
            except ValueError:
                pass

        base_filter = (
            Q(justification__icontains=search) |
            Q(erp_reference__icontains=search) |
            Q(cost_center__icontains=search) |
            Q(items__description__icontains=search) |
            Q(requested_by__first_name__icontains=search) |
            Q(requested_by__last_name__icontains=search)
        )
        if search_id:
            base_filter |= Q(id=search_id)

        queryset = queryset.filter(base_filter).distinct()

    return queryset.order_by('-created_at')

@router.get("/{request_id}", response=PurchaseRequestSchema)
def get_purchase_request(request, request_id: int):
    """
    Detalhe de uma requisição
    """
    purchase_request = get_object_or_404(PurchaseRequest, id=request_id)

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
    attachment = get_object_or_404(Attachment, id=attachment_id)
    
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
                print(f"Erro ao submeter requisição {request_id} em lote: {e}")
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

    workflow = WorkflowService(purchase_request)

    try:
        approval = workflow.approve(user, payload.comments)
        return 200, {"message": "Requisição aprovada com sucesso", "status": purchase_request.status}
    except PermissionError as e:
        return 403, {"message": str(e)}
    except Exception as e:
        return 400, {"message": f"Erro ao aprovar: {str(e)}"}

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
                    delivery_deadline=getattr(item_data, 'delivery_deadline', None),
                    special_status=item_data.special_status,
                    observations=item_data.observations,
                    tax_rate=getattr(item_data, 'tax_rate', None),
                    base_price=getattr(item_data, 'base_price', None)
                )
                changes.append(f"Item {i + 1}: novo item adicionado")

        # Recalcular total
        total = sum([item.total_price or 0 for item in purchase_request.items.all()])
        purchase_request.total_amount = total
        purchase_request.save()

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

@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
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
