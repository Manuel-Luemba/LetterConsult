# api/endpoints.py
from ninja import Router
from ninja.pagination import paginate, PageNumberPagination
from django.shortcuts import get_object_or_404
from django.db.models import Q
from rest_framework.decorators import authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication

from .models import PurchaseRequest, PurchaseRequestItem
from .schemas import *
from core.requisition.schemas import  BulkActionRequest, BulkActionResponse

from .services.PurchasingAnalysisService import PurchasingAnalysisService
from .services.workflow_service import WorkflowService
from ..erp.models import Department
from ..project.models import Project
from .schemas import AnalyzeResponse

router = Router( tags=["Requisition"] )


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
            return {"message": "Você não está alocado neste projeto"}, 403
        department = project.department
    else:
        if payload.department_id:
            department = get_object_or_404(Department, id=payload.department_id)
        else:
            department = user.department

        if not department:
            return {"message": "Departamento não especificado"}, 400

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
            preferred_supplier=(item_data.preferred_supplier.strip() if getattr(item_data, 'preferred_supplier', None) else None),
            delivery_deadline=getattr(item_data, 'delivery_deadline', None),
            special_status=item_data.special_status,
            observations=item_data.observations
        )
        if item.total_price:
            total += item.total_price

    # Atualizar total
    purchase_request.total_amount = total
    purchase_request.save()

    return {"message": "Requisição criada com sucesso", "id": purchase_request.id}

@router.get("/list", response=List[PurchaseRequestSchema])
@paginate(PageNumberPagination, page_size=20)
def list_purchase_requests(request, status: str = None, context: str = None):
    """
    Listar requisições (com filtros)
    """
    user = request.auth
    queryset = PurchaseRequest.objects.all()

    # Filtrar por permissões
    if not user.is_administrator:
        if user.is_purchasing_central:
            # Central vê todas pendentes/compras
            queryset = queryset.filter(
                Q(status__in=['PENDING_PURCHASING', 'PENDING_DIRECTOR_APPROVAL']) |
                Q(requested_by=user)
            )
        elif user.is_director or user.is_deputy_director:
            # Direção vê pendentes direção
            queryset = queryset.filter(
                Q(status='PENDING_DIRECTOR_APPROVAL') |
                Q(requested_by=user)
            )
        else:
            # Outros veem apenas as próprias
            queryset = queryset.filter(requested_by=user)

    # Filtros
    if status:
        queryset = queryset.filter(status=status)
    if context:
        queryset = queryset.filter(context_type=context)

    return queryset.order_by('-created_at')

@router.get("/{request_id}", response=PurchaseRequestSchema)
def get_purchase_request(request, request_id: int):
    """
    Detalhe de uma requisição
    """
    purchase_request = get_object_or_404(PurchaseRequest, id=request_id)

    # Verificar permissão
    user = request.auth
    if not (user.is_administrator or
            user.is_purchasing_central or
            purchase_request.requested_by == user or
            user in purchase_request.all_possible_approvers_for_project_request()):
        return {"message": "Sem permissão para ver esta requisição"}, 403

    return purchase_request

@router.put("/{request_id}", response=MessageResponse)
def update_purchase_request(request, request_id: int, payload: PurchaseRequestUpdate):
    """
    Atualizar requisição (apenas em rascunho)
    """
    purchase_request = get_object_or_404(PurchaseRequest, id=request_id)
    user = request.auth

    # Verificar permissão
    if purchase_request.requested_by != user and not user.is_administrator:
        return {"message": "Apenas o solicitante pode editar"}, 403

    if purchase_request.status != 'DRAFT':
        return {"message": f"Não é possível editar requisição com status {purchase_request.status}"}, 400

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
                preferred_supplier=(item_data.preferred_supplier.strip() if getattr(item_data, 'preferred_supplier', None) else None),
                delivery_deadline=getattr(item_data, 'delivery_deadline', None),
                special_status=item_data.special_status,
                observations=item_data.observations
            )
            if item.total_price:
                total += item.total_price

        purchase_request.total_amount = total
        purchase_request.save()

    return {"message": "Requisição atualizada com sucesso"}

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
        return {"message": "Apenas o solicitante pode submeter"}, 403

    if purchase_request.status != 'DRAFT':
        return {"message": f"Requisição já está com status {purchase_request.status}"}, 400

    # Verificar se tem itens
    if not purchase_request.items.exists():
        return {"message": "Requisição precisa ter pelo menos um item"}, 400

    # Iniciar workflow
    workflow = WorkflowService(purchase_request)
    workflow.submit_for_approval()

    return {"message": "Requisição submetida com sucesso", "status": purchase_request.status}

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
        return {"message": "Requisição aprovada com sucesso", "status": purchase_request.status}
    except PermissionError as e:
        return {"message": str(e)}, 403
    except Exception as e:
        return {"message": f"Erro ao aprovar: {str(e)}"}, 400

@router.post("/{request_id}/rejeitar", response=MessageResponse)
def reject_request(request, request_id: int, payload: RejectAction):
    """
    Rejeitar requisição
    """
    if not payload.reason:
        return {"message": "Motivo da rejeição é obrigatório"}, 400

    purchase_request = get_object_or_404(PurchaseRequest, id=request_id)
    user = request.auth

    workflow = WorkflowService(purchase_request)

    try:
        approval = workflow.reject(user, payload.reason)
        return {"message": "Requisição rejeitada"}
    except PermissionError as e:
        return {"message": str(e)}, 403
    except Exception as e:
        return {"message": f"Erro ao rejeitar: {str(e)}"}, 400

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
        return {"message": "Apenas Central de Compras pode acessar"}, 403

    analysis = PurchasingAnalysisService(purchase_request)
    return analysis.analyze_request()

@router.post("/central-compras/encaminhar/{request_id}", response=MessageResponse)
def forward_to_director(request, request_id: int, payload: ApprovalAction):
    """
    Central de Compras encaminha para direção
    """
    purchase_request = get_object_or_404(PurchaseRequest, id=request_id)
    user = request.auth

    if not user.is_purchasing_central:
        return {"message": "Apenas Central de Compras pode encaminhar"}, 403

    workflow = WorkflowService(purchase_request)

    try:
        workflow.forward_to_director(user, payload.comments)
        return {"message": "Requisição encaminhada para direção"}
    except Exception as e:
        return {"message": f"Erro ao encaminhar: {str(e)}"}, 400

@router.post("/central-compras/editar/{request_id}", response=MessageResponse)
def purchasing_edit(request, request_id: int, payload: PurchaseRequestUpdate):
    """
    Central de Compras edita requisição
    """
    purchase_request = get_object_or_404(PurchaseRequest, id=request_id)
    user = request.auth

    if not user.is_purchasing_central:
        return {"message": "Apenas Central de Compras pode editar"}, 403

    if purchase_request.status != 'PENDING_PURCHASING':
        return {"message": f"Não é possível editar requisição com status {purchase_request.status}"}, 400

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
                item.quantity = item_data.quantity
                item.unit_price = item_data.unit_price
                # Normalize preferred_supplier when editing by Central
                if getattr(item_data, 'preferred_supplier', None) is not None:
                    supplier_val = item_data.preferred_supplier.strip() if item_data.preferred_supplier else None
                    item.preferred_supplier = supplier_val
                # Update delivery_deadline if provided
                if getattr(item_data, 'delivery_deadline', None) is not None:
                    item.delivery_deadline = item_data.delivery_deadline
                item.special_status = item_data.special_status
                item.observations = item_data.observations
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
                    preferred_supplier=(item_data.preferred_supplier.strip() if getattr(item_data, 'preferred_supplier', None) else None),
                    delivery_deadline=getattr(item_data, 'delivery_deadline', None),
                    special_status=item_data.special_status,
                    observations=item_data.observations
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

    return {"message": message}

@router.post("/central-compras/bulk-action", response=BulkActionResponse)
def purchasing_bulk_action(request, payload: BulkActionRequest):
    """
    Executa ações em lote (approve / forward_to_director / reject) sobre várias requisições.
    Somente utilizadores da Central de Compras podem executar.
    """
    user = request.auth

    if not user.is_purchasing_central:
        return {"message": "Apenas Central de Compras pode acessar"}, 403

    # Validação básica
    if not payload.ids or len(payload.ids) == 0:
        return {"success": [], "failed": [{"error": "Nenhum id fornecido"}], "message": "Nenhum id fornecido"}

    if payload.action == 'reject' and not payload.reason:
        return {"success": [], "failed": [{"error": "Motivo obrigatório para rejeição em lote"}], "message": "Motivo obrigatório"}

    workflow_service = WorkflowService(None)  # service will set request per-item

    try:
        results = workflow_service.bulk_process(user, payload.ids, payload.action, comments=payload.comments or '', reason=payload.reason)
        return {"success": results['success'], "failed": results['failed'], "message": "Operação em lote concluída"}
    except PermissionError as e:
        return {"message": str(e), "success": [], "failed": []}, 403
    except ValueError as e:
        return {"message": str(e), "success": [], "failed": []}, 400
    except Exception as e:
        return {"message": f"Erro ao processar em lote: {str(e)}", "success": [], "failed": []}, 400

# ============================================
# WORKFLOW & APPROVALS
# ============================================

# @authentication_classes([JWTAuthentication])
# @permission_classes([IsAuthenticated])
# @router.get("/{request_id}/workflow1", response=WorkflowSchema)
# def get_workflow1(request, request_id: int):
#     """
#     Retorna workflow e histórico de aprovações
#     """
#     purchase_request = get_object_or_404(PurchaseRequest, id=request_id)
#     user = request.auth
#
#     # Verificar permissão
#     if not (user.is_administrator or
#             user.is_purchasing_central or
#             purchase_request.requested_by == user):
#         return {"message": "Sem permissão"}, 403
#
#     workflow = purchase_request.workflow
#     #approvals = workflow.approvals.all()
#     approvals = list(workflow.approvals.all())
#
#     print(approvals, 'worklow')
#
#     return {
#         "current_step": workflow.current_step,
#         "current_step_description": workflow.current_step_description,
#         "requires_project_approval": workflow.requires_project_approval,
#         "requires_department_approval": workflow.requires_department_approval,
#         "requires_director_approval": workflow.requires_director_approval,
#         "started_at": workflow.started_at,
#         "completed_at": workflow.completed_at,
#         "approvals": approvals
#     }



@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@router.get(
    "/{request_id}/workflow",
    response={200: WorkflowSchema, 404: MessageResponse, 403: MessageResponse}
)
def get_workflow(request, request_id: int):

    purchase_request = get_object_or_404(PurchaseRequest, id=request_id)
    user = request.auth

    # 🔒 Permissões
    if not (
        user.is_administrator
        or user.is_purchasing_central
        or purchase_request.requested_by == user
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
            approved_by=getattr(approval.approved_by, "username", None),
            status=approval.status,
            approved_at=approval.approved_at,
        )
        for approval in workflow.approvals.select_related("approved_by").all()
    ]

    return 200, WorkflowSchema(
        current_step=workflow.current_step,
        current_step_description=workflow.current_step_description,
        requires_project_approval=workflow.requires_project_approval,
        requires_department_approval=workflow.requires_department_approval,
        requires_director_approval=workflow.requires_director_approval,
        started_at=workflow.started_at,
        completed_at=workflow.completed_at,
        approvals=approvals,
    )


@router.get("/pendentes", response=List[PurchaseRequestSchema])
def get_pending_approvals(request):
    """
    Lista requisições pendentes de aprovação do utilizador
    """
    user = request.auth

    # Requisições pendentes de aprovação do projeto
    project_approvals = []
    if user.is_team_leader or user.is_project_responsable:
        projects = Project.objects.filter(
            Q(team_leader=user) | Q(responsible=user)
        )
        project_approvals = PurchaseRequest.objects.filter(
            project__in=projects,
            status='PENDING_PROJECT_APPROVAL'
        )

    # Requisições pendentes de aprovação do departamento
    dept_approvals = []
    if user.is_deputy_coordinator or user.is_manager:
        dept_approvals = PurchaseRequest.objects.filter(
            department=user.department,
            status='PENDING_DEPARTMENT_APPROVAL'
        )

    # Requisições pendentes de análise da central
    central_approvals = []
    if user.is_purchasing_central:
        central_approvals = PurchaseRequest.objects.filter(
            status='PENDING_PURCHASING'
        )

    # Requisições pendentes de aprovação da direção
    director_approvals = []
    if user.is_director or user.is_deputy_director:
        director_approvals = PurchaseRequest.objects.filter(
            status='PENDING_DIRECTOR_APPROVAL'
        )

    # Unir todas
    from itertools import chain
    pending = list(chain(
        project_approvals,
        dept_approvals,
        central_approvals,
        director_approvals
    ))

    # Remover duplicados
    seen = set()
    unique_pending = []
    for pr in pending:
        if pr.id not in seen:
            seen.add(pr.id)
            unique_pending.append(pr)

    return unique_pending