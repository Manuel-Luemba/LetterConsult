# api/schemas.py
from ninja import Schema
from typing import List, Optional, Literal, Dict, Any
from datetime import date, datetime
from decimal import Decimal
from pydantic import constr
from core.user.schema import UserOut


# ----- USER SCHEMAS -----
class UserSchema(Schema):
    id: int
    username: str
    first_name: str
    last_name: str
    full_name: str
    email: str
    department_id: Optional[int] = None
    department_name: Optional[str] = None

    class Config:
        orm_mode = True


class UserDetailSchema(UserSchema):
    groups: List[str]
    is_manager: bool
    is_director: bool
    is_purchasing_central: bool

# ----- DEPARTMENT SCHEMAS -----
class DepartmentSchema(Schema):
    id: int
    name: str
    abbreviation: Optional[str] = None
    cost_center: Optional[str] = None
    is_active: bool


# ----- PROJECT SCHEMAS -----
class ProjectSchema(Schema):
    id: int
    name: Optional[str] = None
    cost_center: Optional[str] = None
    department_id: Optional[int] = None
    is_active: bool

# ----- ITEM SCHEMAS -----
class PurchaseRequestItemCreate(Schema):
    description: str
    quantity: Optional[Decimal] = None
    unit_price: Optional[Decimal] = None
    # Urgency at item level: LOW | MEDIUM | HIGH | CRITICAL
    urgency_level: Optional[str] = 'LOW'
    preferred_supplier: Optional[str] = None
    delivery_deadline: Optional[date] = None
    special_status: str = 'NORMAL'
    observations: str = ''
    tax_rate: Optional[Decimal] = None
    base_price: Optional[Decimal] = None

class PurchaseRequestItemSchema(PurchaseRequestItemCreate):
    id: int
    total_price: Optional[Decimal] = None
    preferred_supplier: Optional[str] = None
    delivery_deadline: Optional[date] = None
    tax_rate: Optional[Decimal] = None
    base_price: Optional[Decimal] = None

# ----- ATTACHMENT SCHEMAS -----
class AttachmentBaseSchema(Schema):
    filename: str
    file_size: int
    attachment_type: str
    description: Optional[str] = None
    uploaded_by: UserOut
    uploaded_at: datetime
    
class AttachmentSchema(AttachmentBaseSchema):
    id: int
    file_url: str

    @staticmethod
    def resolve_file_url(obj, context=None):
        if obj.file:
            from django.core.signing import TimestampSigner
            signer = TimestampSigner()
            token = signer.sign(str(obj.id))
            path = f"/api/v1/requisitions/attachments/{obj.id}/download?token={token}"
            
            from crum import get_current_request
            req = context.request if hasattr(context, 'request') else context
            if not req:
                req = get_current_request()
            if req:
                return req.build_absolute_uri(path)
            return path
        return None

# ----- PURCHASE REQUEST SCHEMAS -----
class PurchaseRequestCreate(Schema):
    context_type: str  # 'PROJECT' or 'DEPARTMENT'
    project_id: Optional[int] = None
    department_id: Optional[int] = None
    required_date: date
    reference_month: constr(regex=r"^\d{4}-\d{2}$")  # aceita "2026-03"
    # urgency_level moved to item level
    # Urgency at item level: LOW | MEDIUM | HIGH | CRITICAL
    urgency_level: Optional[str] = 'LOW'
    justification: str
    observations: str = ''
    items: List[PurchaseRequestItemCreate]

class PurchaseRequestUpdate(Schema):
    required_date: Optional[date] = None
    # urgency_level moved to item level
    justification: Optional[str] = None
    observations: Optional[str] = None
    items: Optional[List[PurchaseRequestItemCreate]] = None

class CloneRequestPayload(Schema):
    include_attachments: bool = True

class PurchaseRequestSchema(Schema):
    id: int
    code: str
    context_type: str
    project: Optional[ProjectSchema] = None
    department: Optional[DepartmentSchema] = None
    requested_by: UserOut
    request_date: datetime
    required_date: date
    reference_month: str
    status: str
    # urgency_level removed from request level — use item urgency
    total_amount: Decimal
    justification: str
    observations: str
    cost_center: Optional[str] = None
    is_editable_by_purchasing: bool
    items: List[PurchaseRequestItemSchema]
    attachments: List[AttachmentSchema] = []
    created_at: datetime
    updated_at: datetime
    submitted_at: Optional[datetime] = None
    workflow_metadata: Optional[dict] = None  # 👈 NOVO

    last_edited_by_purchasing_at: Optional[datetime] = None  # 👈 ADICIONAR
    last_edited_by_purchasing_by: Optional[UserOut] = None  # 👈 OPCIONAL

    days_remaining: Optional[int] = None
    is_urgent: bool = False
    can_current_user_approve: bool = False
    my_assignment_status: Optional[str] = None
    my_assignment_id: Optional[int] = None
    
    other_approvers_pending: int = 0
    purchasing_actions: List[dict] = []
    approved_by: Optional[dict] = None
    approved_at: Optional[datetime] = None

    @staticmethod
    def resolve_days_remaining(obj):
        """Calcula dias restantes para entrega"""
        if not obj.required_date:
            return None
        delta = obj.required_date - date.today()
        return delta.days

    @staticmethod
    def resolve_is_urgent(obj):
        """Determina se requisição é urgente (baseado nos itens e prazo)."""
        # 1) Verifica se algum item tem urgency HIGH/CRITICAL
        try:
            items = getattr(obj, 'items', [])
            for item in items.all() if hasattr(items, 'all') else items:
                if getattr(item, 'urgency_level', None) in ['HIGH', 'CRITICAL']:
                    return True
        except Exception:
            pass

        # 2) Por prazo (<= 2 dias)
        if getattr(obj, 'required_date', None):
            days = (obj.required_date - date.today()).days
            if days <= 2:
                return True

        return False

    @staticmethod
    def resolve_can_current_user_approve(obj, context=None):
        """Verifica se o utilizador atual pode aprovar esta requisição."""
        from crum import get_current_request
        
        # Tenta obter o request diretamente do context
        request = context
        if hasattr(context, 'request'):
            request = context.request

        if request is None:
            request = get_current_request()

        if request is None:
            return False

        user = getattr(request, 'auth', getattr(request, 'user', None))
        if not user or not user.is_authenticated:
            return False

        # Central de Compras
        if getattr(user, 'is_purchasing_central', False) and obj.status == 'PENDING_PURCHASING':
            return True

        # Direção
        if (getattr(user, 'is_director', False) or getattr(user, 'is_deputy_director', False)) and obj.status == 'PENDING_DIRECTOR_APPROVAL':
            return True

        # Projeto
        if obj.context_type == 'PROJECT' and obj.status == 'PENDING_PROJECT_APPROVAL':
            try:
                return user.id in [u.id for u in obj.project.all_approvers]
            except Exception:
                return False

        # Departamento
        if obj.context_type == 'DEPARTMENT' and obj.status == 'PENDING_DEPARTMENT_APPROVAL':
            try:
                return user.id in [u.id for u in obj.department.all_approvers]
            except Exception:
                return False

        return False

    @staticmethod
    def _get_user_assignment(obj, context):
        from crum import get_current_request
        request = context
        if hasattr(context, 'request'):
            request = context.request
        if request is None:
            request = get_current_request()
        if request is None:
            return None
        
        user = getattr(request, 'auth', getattr(request, 'user', None))
        if not user or not getattr(user, 'is_authenticated', False) or not getattr(user, 'pk', None):
            return None

        # Usar filter() em vez de get() porque as vezes os testes podem injetar lixo e `.first()` é mais seguro
        return obj.assignments.filter(approver=user).order_by('-assigned_at').first()

    @staticmethod
    def resolve_my_assignment_status(obj, context=None):
        assignment = PurchaseRequestSchema._get_user_assignment(obj, context)
        return assignment.status if assignment else None

    @staticmethod
    def resolve_my_assignment_id(obj, context=None):
        assignment = PurchaseRequestSchema._get_user_assignment(obj, context)
        return assignment.id if assignment else None

    @staticmethod
    def resolve_other_approvers_pending(obj, context=None):
        from crum import get_current_request
        request = context.request if hasattr(context, 'request') else context
        if not request:
            request = get_current_request()
        user = getattr(request, 'auth', getattr(request, 'user', None)) if request else None
        # Guard against AnonymousUser or missing user
        if not user or not getattr(user, 'is_authenticated', False) or not getattr(user, 'pk', None):
            return 0
        return obj.assignments.filter(status='PENDING').exclude(approver=user).count()

    @staticmethod
    def resolve_purchasing_actions(obj):
        # Filtra as aprovações da central (ou seja, feitas na etapa PURCHASING_ANALYSIS ou com ação de FORWARD)
        actions = obj.approvals.filter(action__in=['FORWARD', 'EDIT', 'APPROVE'], step='PURCHASING_ANALYSIS').order_by('approved_at')
        return [
            {
                "action": a.action,
                "performed_by": {
                    "id": a.approver.id,
                    "full_name": a.approver.get_full_name() or a.approver.username,
                    "email": a.approver.email,
                },
                "performed_at": a.approved_at,
                "comments": a.comments,
                "target_step": None # Can be expanded if needed
            } for a in actions
        ]

    @staticmethod
    def resolve_approved_by(obj):
        # Obtém o último gestor a aprovar
        last_approval = obj.approvals.filter(action='APPROVE').exclude(step='PURCHASING_ANALYSIS').order_by('-approved_at').first()
        if last_approval:
            return {
                "id": last_approval.approver.id,
                "full_name": last_approval.approver.get_full_name() or last_approval.approver.username,
                "role": "Approver" 
            }
        return None

    @staticmethod
    def resolve_approved_at(obj):
        last_approval = obj.approvals.filter(action='APPROVE').exclude(step='PURCHASING_ANALYSIS').order_by('-approved_at').first()
        if last_approval:
            return last_approval.approved_at
        return None

    @staticmethod
    def resolve_workflow_metadata(obj):
        """Calcula metadados de progresso do workflow para a barra de progresso."""
        try:
            # Tentar obter o workflow do cache ou do objeto
            workflow = getattr(obj, 'workflow', None)
            if not workflow:
                return None
                
            current_step = workflow.current_step
            if current_step == 'DRAFT':
                return None

            # Determinar passos totais
            # 1. Aprovação Local (Projeto/Dept)
            # 2. Central de Compras (Purchasing Analysis)
            # 3. Direção (se necessário)
            
            total_steps = 2 # Mínimo (Aprovação Local + Central)
            
            # Se já sabemos que requer direção ou está na direção, o total é 3
            if workflow.requires_director_approval or current_step == 'DIRECTOR_APPROVAL' or obj.status == 'PENDING_DIRECTOR_APPROVAL':
                total_steps = 3
            
            current_index = 0
            if current_step in ['PROJECT_APPROVAL', 'DEPARTMENT_APPROVAL']:
                current_index = 1
            elif current_step == 'PURCHASING_ANALYSIS':
                current_index = 2
            elif current_step == 'DIRECTOR_APPROVAL':
                current_index = 3
            elif current_step in ['APPROVED', 'COMPLETED']:
                current_index = total_steps
            elif current_step == 'REJECTED':
                 current_index = total_steps # Estado final
                 
            return {
                "current_step_index": current_index,
                "total_steps": total_steps,
                "current_step_label": workflow.current_step_description
            }
        except Exception:
            return None

    @classmethod
    def from_orm(cls, obj):
        # Use default pydantic conversion first
        instance = super().from_orm(obj)

        # Ensure requested_by is converted via UserOut.from_orm to populate full_name, etc.
        try:
            if getattr(obj, 'requested_by', None):
                instance.requested_by = UserOut.from_orm(obj.requested_by)
        except Exception:
            # fallback: leave whatever pydantic placed or None
            pass

        # last_edited_by_purchasing_by may be a FK to User — convert if present
        try:
            if getattr(obj, 'last_edited_by_purchasing_by', None):
                instance.last_edited_by_purchasing_by = UserOut.from_orm(obj.last_edited_by_purchasing_by)
        except Exception:
            pass

        return instance

# ----- WORKFLOW SCHEMAS -----
class ApprovalSchema(Schema):
    id: int
    approver: UserSchema
    approved_at: datetime
    action: str
    step: str
    comments: str

    class Config:
        orm_mode = True


class WorkflowSchema(Schema):
    current_step: str
    current_step_description: str
    requires_project_approval: bool
    requires_department_approval: bool
    requires_director_approval: bool
    started_at: datetime
    completed_at: Optional[datetime] = None
    approvals: List[ApprovalSchema]
    can_current_user_approve: bool = False  # 👈 NOVO CAMPO

# ----- ACTION SCHEMAS -----
class ApprovalAction(Schema):
    comments: str = ''

class RejectAction(Schema):
    reason: str

# ----- BULK ACTION SCHEMAS -----
class BulkActionRequest(Schema):
    ids: List[int]
    action: Literal['approve', 'forward_to_director', 'reject']
    comments: Optional[str] = ''
    reason: Optional[str] = None  # Obrigatório quando action == 'reject'

class BulkActionResult(Schema):
    id: int
    status: str  # 'success' | 'error'
    action: str
    message: Optional[str] = None

class BulkActionResponse(Schema):
    success: List[int]
    failed: List[Dict[str, Any]]
    message: str

# ----- RESPONSE SCHEMAS -----
class MessageResponse(Schema):
    message: str
    id: Optional[int] = None
    status: Optional[str] = None

# ----- MISSING ITEM DETAIL (used by PurchasingAnalysisService) -----
class MissingItemDetail(Schema):
    item_id: int
    description: Optional[str] = None
    missing: List[str]
    quantity: Optional[Decimal] = None
    current_unit_price: Optional[Decimal] = None

class AnalyzeResponse(Schema):
    request_id: int
    code: str
    context: Optional[str] = None
    project: Optional[str] = None
    department: Optional[str] = None

    total_amount: Decimal
    formatted_total: str
    items_count: int
    items_with_price: int
    has_incomplete_items: bool
    items_with_supplier: int
    has_items_without_supplier: bool
    items_without_supplier_count: int
    items_missing_details: List[MissingItemDetail]

    requires_director_approval: bool
    director_approval_reason: str
    company_limit: Decimal
    formatted_limit: str

    current_status: str
    submitted_at: Optional[datetime] = None

    recommendation: Dict[str, Any]

class BulkSubmitSchema(Schema):
    request_ids: List[int]
    comments: Optional[str] = None

class BulkSubmitResponse(Schema):
    success: bool
    submitted_count: int
    failed_count: int
    message: str
