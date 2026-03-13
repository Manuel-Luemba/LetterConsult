from django.db import models
from django.db.models import Model
from core.erp.models import Department
from core.project.models import Project
from core.user.models import User

# class Supplier(models.Model):
#     """
#     Representa um fornecedor.
#     - Utilizado como fornecedor preferencial nas requisições.
#     - Pode ser associado a itens no futuro.
#     """
#     code = models.CharField(
#         max_length=50,
#         unique=True,
#         verbose_name='Supplier Code'
#     )
#     name = models.CharField(
#         max_length=200,
#         verbose_name='Supplier Name'
#     )
#     tax_id = models.CharField(
#         max_length=50,
#         verbose_name='Tax ID / NIF',
#         blank=True
#     )
#     email = models.EmailField(
#         verbose_name='Email',
#         blank=True
#     )
#     phone = models.CharField(
#         max_length=50,
#         verbose_name='Phone',
#         blank=True
#     )
#     address = models.TextField(
#         verbose_name='Address',
#         blank=True
#     )
#     payment_terms = models.IntegerField(
#         verbose_name='Payment Terms (days)',
#         default=30,
#         help_text='Default payment terms in days'
#     )
#     is_active = models.BooleanField(
#         verbose_name='Active',
#         default=True
#     )
#
#     created_at = models.DateTimeField(auto_now_add=True)
#     updated_at = models.DateTimeField(auto_now=True)
#
#     class Meta:
#         db_table = 'supplier'
#         verbose_name = 'Supplier'
#         verbose_name_plural = 'Suppliers'
#         ordering = ['name']
#
# def __str__(self):
#     return f"{self.code} - {self.name}"

class ItemCategory(models.Model):
    """
    Categoria de itens/bens/serviços.
    - Utilizado para agrupar itens similares.
    - Pode ser usado em regras de aprovação (ex: categorias acima de X valor vão para direção).
    """
    code = models.CharField(
        max_length=50,
        unique=True,
        verbose_name='Category Code'
    )
    name = models.CharField(
        max_length=200,
        verbose_name='Category Name'
    )
    description = models.TextField(
        verbose_name='Description',
        blank=True
    )
    requires_director_approval = models.BooleanField(
        verbose_name='Requires Director Approval',
        default=False,
        help_text='All items in this category require director approval'
    )

    director_approval_threshold = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Director Approval Threshold',
        help_text='If item value exceeds this, requires director approval'
    )
    is_active = models.BooleanField(
        verbose_name='Active',
        default=True
    )

    class Meta:
        db_table = 'item_category'
        verbose_name = 'Item Category'
        verbose_name_plural = 'Item Categories'
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.name}"


class PurchaseRequest(models.Model):
    """
    Representa uma requisição de compra.
    - Pode ser contextual: PROJETO ou DEPARTAMENTO (mutuamente exclusivos).
    - Passa por um workflow de aprovações.
    - Contém um ou mais itens.
    """
    # ----- CONTEXTO (MUTUAMENTE EXCLUSIVO) -----
    CONTEXT_TYPES = [
        ('PROJECT', 'Project Request'),
        ('DEPARTMENT', 'Department Request'),
    ]

    #Status e Workflow
    BUSINESS_UNIT_CHOICES = [
        ('AS', 'Ambiente e Social'),
        ('ENG', 'Engenharia'),
        ('ARQ', 'Arquitetura'),
        ('CONSU', 'Consultoria'),
        ('FISC', 'Fiscalização'),
        ('SEDE', 'Sede'),
    ]

    context_type = models.CharField(
        max_length=20,
        choices=CONTEXT_TYPES,
        verbose_name='Request Context',
        help_text='Is this request for a project or for a department?'
    )

    project = models.ForeignKey(
        Project,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='purchase_requests',
        verbose_name='Project',
        help_text='Required if context is PROJECT'
    )

    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='purchase_requests',
        verbose_name='Department',
        help_text='Required if context is DEPARTMENT'
    )

    business_unit = models.CharField(max_length=100, choices=BUSINESS_UNIT_CHOICES, null=True, blank=True,
                                     verbose_name='Unidade de negocio')

    # ----- SOLICITANTE -----
    requested_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='purchase_requests',
        verbose_name='Requested By'
    )

    # ----- DATAS -----
    request_date = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Request Date'
    )

    required_date = models.DateField(
        verbose_name='Required Delivery Date'
    )

    # reference_month = models.DateField(
    #     verbose_name='Reference Month',
    #     help_text='Month this request is budgeted for'
    # )

    reference_month = models.CharField(
        max_length=7,  # "YYYY-MM" → 7 caracteres
        verbose_name="Reference Month",
        help_text="Month this request is budgeted for"
    )

    # ----- STATUS E URGÊNCIA -----
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('PENDING_PROJECT_APPROVAL', 'Pending Project Approval'),
        ('PENDING_DEPARTMENT_APPROVAL', 'Pending Department Approval'),
        ('PENDING_PURCHASING', 'Pending Purchasing Analysis'),
        ('PENDING_DIRECTOR_APPROVAL', 'Pending Director Approval'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
        ('CANCELLED', 'Cancelled'),
        ('ORDERED', 'Ordered'),
        ('PARTIALLY_RECEIVED', 'Partially Received'),
        ('COMPLETED', 'Completed'),
    ]

    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default='DRAFT',
        verbose_name='Status'
    )
    cost_center = models.CharField(
        max_length=50,
        verbose_name="Cost Center",
        help_text="Centro de custo associado à requisição",
        null=True,
        blank=True
    )

    # ----- VALORES -----
    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name='Total Amount',
        editable=False,
    )

    # ----- TEXTOS -----
    justification = models.TextField(
        verbose_name='Justification',
        help_text='Why is this purchase necessary?'
    )
    observations = models.TextField(
        verbose_name='Observations',
        blank=True
    )

    # ----- CONTROLO DE EDIÇÃO PELA CENTRAL DE COMPRAS -----
    is_editable_by_purchasing = models.BooleanField(
        default=True,
        verbose_name='Editable by Purchasing',
        help_text='Whether purchasing central can edit this request'
    )

    last_edited_by_purchasing_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Last Edited by Purchasing At'
    )

    last_edited_by_purchasing_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='purchasing_edited_requests',
        verbose_name='Last Edited by Purchasing By'
    )

    # ----- AUDITORIA -----
    created_at = models.DateTimeField(auto_now_add=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True, blank=True)

    submitted_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Submitted At'
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Completed At'
    )

    # ----- ERP SYNC FIELDS (preparação para integração futura) -----
    ERP_SYNC_STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('SYNCED', 'Synced'),
        ('FAILED', 'Failed'),
    ]

    erp_sync_status = models.CharField(
        max_length=20,
        choices=ERP_SYNC_STATUS_CHOICES,
        default='SYNCED',
        verbose_name='ERP Sync Status',
        help_text='Estado da sincronização com o ERP (mock)'
    )

    erp_reference = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        verbose_name='ERP Reference',
        help_text='Referência retornada pelo ERP após sincronização'
    )

    class Meta:
        db_table = 'purchase_request'
        verbose_name = 'Purchase Request'
        verbose_name_plural = 'Purchase Requests'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['context_type']),
            models.Index(fields=['requested_by', 'status']),
        ]

        permissions = [
            ('edit_purchaserequest_purchasing', 'Can edit purchase request (purchasing level)'),
        ]

    def all_possible_approvers_for_project_request(self):
        """
        Para requisições de PROJETO:
        - Aprovadores do projeto (responsables + team leader)
        - Coordenadores do departamento (managers + deputy)
        """
        if self.context_type != 'PROJECT' or not self.project:
            return []

        project_approvers = self.project.all_approvers
        dept_approvers = self.project.department.all_approvers if self.project.department else []

        from itertools import chain
        all_approvers = set(chain(project_approvers, dept_approvers))
        return list(all_approvers)

    def __str__(self):
        return f"{self.code} - {self.effective_department} - {self.status}"

    def clean(self):
        """Validações de contexto mutuamente exclusivo."""
        from django.core.exceptions import ValidationError

        if self.context_type == 'PROJECT':
            if not self.project:
                raise ValidationError({'project': 'Project is required for PROJECT context.'})
            if self.department:
                raise ValidationError({'department': 'Department must be empty for PROJECT context.'})
        elif self.context_type == 'DEPARTMENT':
            if not self.department:
                raise ValidationError({'department': 'Department is required for DEPARTMENT context.'})
            if self.project:
                raise ValidationError({'project': 'Project must be empty for DEPARTMENT context.'})

    def save(self, *args, **kwargs):
        self.clean()
        # Preenche automaticamente se não foi definido
        if not self.cost_center:
            if self.context_type == 'PROJECT' and self.project:
                self.cost_center = self.project.cost_center
            elif  self.context_type == 'DEPARTMENT' and self.department:
                self.cost_center = self.department.cost_center
        super().save(*args, **kwargs)

    @property
    def effective_department(self):
        """Retorna o departamento efetivo (projeto.department ou department)."""
        if self.context_type == 'PROJECT' and self.project:
            return self.project.department
        return self.department

    @property
    def derived_cost_center(self):
        """Retorna o centro de custo da requisição."""
        if self.context_type == 'PROJECT' and self.project:
            return self.project.cost_center
        elif self.context_type == 'DEPARTMENT' and self.department:
            return self.department.cost_center
        return None

    @property
    def code(self):
        """Código interno da requisição (ex: RC-TI-2026-000001)."""
        from django.utils.timezone import now
        year = self.created_at.year if self.created_at else now().year
        
        # Obtém abreviatura do departamento (TI, RH, etc)
        dept = self.effective_department
        abbr = dept.abbreviation.upper() if dept and dept.abbreviation else "DEP"
        
        return f"RC-{abbr}-{year}-{self.id:06d}" if self.id else "NOVO"


    def user_can_approve_current_step(self, user):
        """
        Verifica se um utilizador pode aprovar a requisição no passo atual
        """
        # Central de Compras
        if user.is_purchasing_central and self.status == 'PENDING_PURCHASING':
            return True

        # Direção
        if (user.is_director or user.is_deputy_director) and self.status == 'PENDING_DIRECTOR_APPROVAL':
            return True

        # Projeto
        if self.context_type == 'PROJECT' and self.status == 'PENDING_PROJECT_APPROVAL':
            if hasattr(self, 'project') and self.project:
                return user.id in [u.id for u in self.project.all_approvers]

        # Departamento
        if self.context_type == 'DEPARTMENT' and self.status == 'PENDING_DEPARTMENT_APPROVAL':
            if hasattr(self, 'department') and self.department:
                return user.id in [u.id for u in self.department.all_approvers]

        return False

class PurchaseRequestItem(Model):
    """
    Item/linha de uma requisição de compra.
    - Uma requisição pode ter múltiplos itens.
    - Cada item tem quantidade, valor unitário e total.
    - Pode ter fornecedor preferencial específico.
    """

    # Casos especiais
    IS_SPECIAL_CHOICES = [
        ('NORMAL', 'Normal'),
        ('CONSULT', 'Under Consultation'),
        ('TO_DEFINE', 'To Define'),
    ]

    URGENCY_LEVELS = [
        ('LOW', 'Low'),
        ('MEDIUM', 'Medium'),
        ('HIGH', 'High'),
        ('CRITICAL', 'Critical'),
    ]

    purchase_request = models.ForeignKey(
        PurchaseRequest,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name='Purchase Request'
    )

    # Descrição (pode ser livre ou referenciar categoria)
    description = models.TextField(
        verbose_name='Item Description'
    )

    urgency_level = models.CharField(
        max_length=20,
        choices=URGENCY_LEVELS,
        verbose_name='Urgency Level'
    )

    # category = models.ForeignKey(
    #     ItemCategory,
    #     on_delete=models.SET_NULL,
    #     null=True,
    #     blank=True,
    #     related_name='items',
    #     verbose_name='Category'
    # )

    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name='Quantity',
        default=1
    )
    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name='Unit Price',
        null=True,
        blank=True
    )
    tax_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Tax Rate'
    )
    base_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Base Price'
    )

    total_price = models.DecimalField( max_digits=12, decimal_places=2, verbose_name='Total Price',
        editable=False,
        null=True,
        blank=True
    )

    # Fornecedor preferencial (opcional por item)
    preferred_supplier = models.CharField(
        max_length=200,
        null=True,
        blank=True,
        verbose_name='Preferred Supplier'
    )

    special_status = models.CharField(
        max_length=20,
        choices=IS_SPECIAL_CHOICES,
        default='NORMAL',
        verbose_name='Special Status',
        help_text='For "Sob Consulta" or "A Definir" cases'
    )

    # Observações por item
    observations = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='Observations'
    )
    delivery_deadline = models.DateField(verbose_name='Delivery Deadline', null=True, blank=True)
    class Meta:
        db_table = 'purchase_request_item'
        verbose_name = 'Request Item'
        verbose_name_plural = 'Request Items'

    def __str__(self):
        return f"{self.purchase_request.code} - {self.description[:50]}"

    def save(self, *args, **kwargs):
        """Calcula o total_price automaticamente."""
        # Se não houver quantity definido, usar default (1) — campo já tem default
        if self.unit_price is not None:
            # garante que quantity não é None
            qty = self.quantity if self.quantity is not None else 1
            self.total_price = qty * self.unit_price
        else:
            # Mantém None quando não existe price
            self.total_price = None
        super().save(*args, **kwargs)

class ApprovalWorkflow(models.Model):
    """
    Workflow de aprovação de uma requisição.
    - Define o estado atual e os aprovadores de cada etapa.
    - É criado automaticamente quando a requisição é submetida.
    """

    STEP_CHOICES = [
        ('DRAFT', 'Draft'),
        ('PROJECT_APPROVAL', 'Awaiting Project Approval'),
        ('DEPARTMENT_APPROVAL', 'Awaiting Department Approval'),
        ('PURCHASING_ANALYSIS', 'Awaiting Purchasing Analysis'),
        ('DIRECTOR_APPROVAL', 'Awaiting Director Approval'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
        ('CANCELLED', 'Cancelled'),
    ]

    purchase_request = models.OneToOneField(
        PurchaseRequest,
        on_delete=models.CASCADE,
        related_name='workflow',
        verbose_name='Purchase Request'
    )

    current_step = models.CharField(
        max_length=30,
        choices=STEP_CHOICES,
        default='DRAFT',
        verbose_name='Current Step'
    )

    # ----- FLAGS DE FLUXO -----
    requires_project_approval = models.BooleanField(
        default=False,
        verbose_name='Requires Project Approval'
    )
    requires_department_approval = models.BooleanField(
        default=False,
        verbose_name='Requires Department Approval'
    )
    requires_director_approval = models.BooleanField(
        default=False,
        verbose_name='Requires Director Approval'
    )

    # ----- APROVADORES (NÃO FIXOS - VALIDAÇÃO DINÂMICA) -----
    # Estes campos são informativos, a validação é feita por regras

    # ----- TIMELINE -----
    started_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Started At'
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Completed At'
    )

    class Meta:
        db_table = 'approval_workflow'
        verbose_name = 'Approval Workflow'
        verbose_name_plural = 'Approval Workflows'

    def __str__(self):
        return f"Workflow - {self.purchase_request.code} - {self.current_step}"

    @property
    def current_step_description(self):
        """Descrição amigável da etapa atual."""
        descriptions = {
            'DRAFT': 'Rascunho',
            'PROJECT_APPROVAL': 'Aguardando aprovação do projeto',
            'DEPARTMENT_APPROVAL': 'Aguardando aprovação do departamento',
            'PURCHASING_ANALYSIS': 'Em análise pela Central de Compras',
            'DIRECTOR_APPROVAL': 'Aguardando aprovação da Direção',
            'APPROVED': 'Aprovado',
            'REJECTED': 'Rejeitado',
            'CANCELLED': 'Cancelado',
        }
        return descriptions.get(self.current_step, self.current_step)

class Approval(models.Model):
    """
        Registo individual de cada ação no workflow.
        - Mantém histórico completo de todas as aprovações/rejeições/edições.
        - Permite auditoria e rastreabilidade.
    """

    """
    Registo individual de cada aprovação ou rejeição.
    - Mantém histórico completo de todas as ações no workflow.
    - Permite auditoria e rastreabilidade.
    """

    ACTION_CHOICES = [
        ('APPROVE', 'Approved'),
        ('REJECT', 'Rejected'),
        ('FORWARD', 'Forwarded to Director'),
        ('CANCEL', 'Cancelled'),
        ('EDIT', 'Edited by Purchasing'),  # Ação de edição pela central
    ]

    purchase_request = models.ForeignKey(
        PurchaseRequest,
        on_delete=models.CASCADE,
        related_name='approvals',
        verbose_name='Purchase Request'
    )

    workflow = models.ForeignKey(
        ApprovalWorkflow,
        on_delete=models.CASCADE,
        related_name='approvals',
        verbose_name='Workflow'
    )

    # Quem e quando
    approver = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='approvals_given',
        verbose_name='Approver'
    )
    approved_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Approved At'
    )

    # Ação tomada
    action = models.CharField(
        max_length=20,
        choices=ACTION_CHOICES,
        verbose_name='Action'
    )

    # Etapa em que foi tomada
    step = models.CharField(
        max_length=30,
        choices=ApprovalWorkflow.STEP_CHOICES,
        verbose_name='Step'
    )

    # Comentários
    comments = models.TextField(
        verbose_name='Comments',
        blank=True
    )

    # Se action == 'EDIT' podemos guardar um diff/JSON com as alterações feitas
    changes_json = models.JSONField(
        null=True,
        blank=True,
        verbose_name='Changes JSON',
        help_text='Detalhes das alterações quando action == EDIT'
    )

    class Meta:
        db_table = 'approval'
        verbose_name = 'Approval'
        verbose_name_plural = 'Approvals'
        ordering = ['-approved_at']
        indexes = [
            models.Index(fields=['purchase_request', 'approved_at']),
        ]

    def __str__(self):
        return f"{self.action} - {self.purchase_request.code} - {self.approver.get_full_name()}"


def attachment_upload_path(instance, filename):
    """Gera caminho único para anexos."""
    from django.utils import timezone
    ext = filename.split('.')[-1]
    date_path = timezone.now().strftime('%Y/%m')
    new_filename = f"PR-{instance.purchase_request.id:06d}_{instance.uploaded_by.id}_{timezone.now().strftime('%H%M%S')}.{ext}"
    return f'purchase_requests/{date_path}/{new_filename}'

class Attachment(models.Model):
    """
    Anexos de uma requisição de compra.
    - Orçamentos, propostas comerciais, faturas, etc.
    """
    purchase_request = models.ForeignKey(
        PurchaseRequest,
        on_delete=models.CASCADE,
        related_name='attachments',
        verbose_name='Purchase Request'
    )

    file = models.FileField(
        upload_to=attachment_upload_path,
        verbose_name='File'
    )
    filename = models.CharField(
        max_length=255,
        verbose_name='Filename'
    )
    file_size = models.IntegerField(
        verbose_name='File Size (bytes)'
    )

    ATTACHMENT_TYPES = [
        ('QUOTATION', 'Quotation'),
        ('INVOICE', 'Invoice'),
        ('CONTRACT', 'Contract'),
        ('SPECIFICATION', 'Specification'),
        ('OTHER', 'Other'),
    ]

    attachment_type = models.CharField(
        max_length=20,
        choices=ATTACHMENT_TYPES,
        default='OTHER',
        verbose_name='Attachment Type'
    )

    description = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='Description'
    )

    uploaded_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='uploaded_attachments',
        verbose_name='Uploaded By'
    )
    uploaded_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Uploaded At'
    )

    class Meta:
        db_table = 'attachment'
        verbose_name = 'Attachment'
        verbose_name_plural = 'Attachments'

    def __str__(self):
        return f"{self.purchase_request.code} - {self.filename}"

    def save(self, *args, **kwargs):
        """Preenche filename e file_size automaticamente."""
        import os
        if self.file and not self.filename:
            self.filename = os.path.basename(self.file.name)
        if self.file and not self.file_size:
            self.file_size = self.file.size
        super().save(*args, **kwargs)

class PurchaseRequestAssignment(models.Model):
    """
    Representa a atribuição pendente de uma requisição a um aprovador.
    (Inbox/Caixa de Entrada de tarefas do gestor).
    - Criado automaticamente quando o workflow transita para uma etapa de aprovação.
    - Resolvido (COMPLETED/OBSOLETE) quando alguém da mesma 'pool' aprova/rejeita a requisição.
    """

    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('COMPLETED', 'Completed'),
        ('REJECTED', 'Rejected'),
        ('OBSOLETE', 'Obsolete'),  # Quando outro manager aprova antes
    ]

    purchase_request = models.ForeignKey(
        PurchaseRequest,
        on_delete=models.CASCADE,
        related_name='assignments',
        verbose_name='Purchase Request'
    )

    approver = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='assigned_requests',
        verbose_name='Approver'
    )

    step = models.CharField(
        max_length=30,
        choices=ApprovalWorkflow.STEP_CHOICES,
        verbose_name='Workflow Step'
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='PENDING',
        verbose_name='Status'
    )

    assigned_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Assigned At'
    )

    class Meta:
        db_table = 'purchase_request_assignment'
        verbose_name = 'Purchase Request Assignment'
        verbose_name_plural = 'Purchase Request Assignments'
        ordering = ['-assigned_at']
        indexes = [
            models.Index(fields=['approver', 'status']),
            models.Index(fields=['purchase_request', 'status']),
        ]

    def __str__(self):
        return f"{self.status} - {self.purchase_request.code} - {self.approver.get_full_name()}"
