# services/workflow_service.py
from django.db import transaction
from django.utils import timezone
from ..models import ApprovalWorkflow, Approval, PurchaseRequestAssignment
from .notification_service import NotificationService
from .PurchasingAnalysisService import PurchasingAnalysisService
import logging
from django.conf import settings

logger = logging.getLogger(__name__)


class WorkflowService:
    """
    Serviço responsável por gerir todo o fluxo de aprovações
    """

    def __init__(self, purchase_request):
        self.request = purchase_request
        self.notifications = NotificationService()

    @transaction.atomic
    def submit_for_approval(self):
        """
        Submete requisição para aprovação (inicia workflow)
        """
        logger.info(f"Submitting request {self.request.id} for approval")

        # 1. Atualizar status
        self.request.status = self._get_initial_status()
        self.request.submitted_at = timezone.now()
        self.request.save()

        # 2. Criar ou atualizar workflow
        workflow, created = ApprovalWorkflow.objects.get_or_create(
            purchase_request=self.request
        )

        # 3. Determinar fluxo baseado no contexto e quem preencheu
        if self.request.context_type == 'PROJECT':
            self._setup_project_workflow(workflow)
        else:
            self._setup_department_workflow(workflow)

        workflow.save()

        # 4. Notificar próximos aprovadores
        self._notify_next_approvers(workflow)

        logger.info(f"Workflow setup completed for request {self.request.id}")
        return workflow

    @transaction.atomic
    def approve(self, approver, comments=""):
        """
        Processa uma aprovação
        """
        logger.info(f"Processing approval for request {self.request.id} by {approver.username}")

        workflow = self.request.workflow

        # 1. Validar se user pode aprovar
        if not self._can_approve(approver, workflow.current_step):
            raise PermissionError(f"User {approver.username} cannot approve at step {workflow.current_step}")

        # Se estivermos na etapa de análise pela Central, garantir que todos os itens têm preço antes de aprovar
        if workflow.current_step == 'PURCHASING_ANALYSIS' and approver.groups.filter(name='PurchasingCentral').exists():
            try:
                analysis = PurchasingAnalysisService(self.request)
                totals = analysis.calculate_totals()
                if totals.get('has_items_without_price'):
                    raise ValueError('Existem itens sem preço. Preencha os preços antes de aprovar.')
                if totals.get('has_items_without_supplier'):
                    raise ValueError(f'Existem {totals.get("items_without_supplier_count")} item(s) sem fornecedor preferido. A Central deve indicar o fornecedor antes de aprovar.')
            except Exception:
                # Propagar erros de validação para o caller
                raise

        # 2. Registar aprovação
        approval = Approval.objects.create(
            purchase_request=self.request,
            workflow=workflow,
            approver=approver,
            action='APPROVE',
            step=workflow.current_step,
            comments=comments
        )

        # 2.5 Notificar outros membros do grupo (se aplicável) que "já aprovado por {approver}".
        try:
            # Determine groups to notify based on the current step
            if workflow.current_step == 'PROJECT_APPROVAL':
                group_names = ['TeamLeader', 'ProjectResponsable', 'AdministrativeStaff']
            elif workflow.current_step == 'DEPARTMENT_APPROVAL':
                group_names = ['Manager', 'DeputyManager']
            else:
                group_names = []

            if group_names:
                self.notifications.notify_group_approval(self.request, group_names, approver)
        except Exception:
            logger.exception('Failed to notify group about approval')
            
        # 2.6 Limpar Assignments da etapa atual (Inbox)
        self._clear_step_assignments(workflow.current_step, approver, 'COMPLETED')

        # 3. Avançar workflow
        self._advance_workflow(workflow, approver)

        logger.info(f"Approval registered for request {self.request.id}")
        return approval

    @transaction.atomic
    def reject(self, approver, reason):
        """
        Processa uma rejeição
        """
        logger.info(f"Processing rejection for request {self.request.id} by {approver.username}")

        if not reason:
            raise ValueError("Reason is required for rejection")

        workflow = self.request.workflow

        # 1. Validar se user pode rejeitar
        if not self._can_approve(approver, workflow.current_step):
            raise PermissionError(f"User {approver.username} cannot reject at step {workflow.current_step}")

        # 2. Registar rejeição
        approval = Approval.objects.create(
            purchase_request=self.request,
            workflow=workflow,
            approver=approver,
            action='REJECT',
            step=workflow.current_step,
            comments=reason
        )

        # 3. Atualizar status
        self.request.status = 'REJECTED'
        self.request.save()

        workflow.current_step = 'REJECTED'
        workflow.completed_at = timezone.now()
        workflow.save()

        # 3.5 Limpar Assignments da etapa atual (Inbox)
        # O approver atual é marcado como REJECTED (pois fez a ação de reject), os outros como OBSOLETE
        self._clear_step_assignments(workflow.current_step, approver, 'REJECTED')

        # 4. NOTIFICAR SOLICITANTE (obrigatório)
        self.notifications.notify_requestor_rejected(self.request, approver, reason)

        logger.info(f"Request {self.request.id} rejected")
        return approval

    @transaction.atomic
    def forward_to_director(self, approver, comments=""):
        """
        Central de Compras encaminha para direção
        """
        logger.info(f"Forwarding request {self.request.id} to director by {approver.username}")

        workflow = self.request.workflow

        # 1. Registar encaminhamento
        approval = Approval.objects.create(
            purchase_request=self.request,
            workflow=workflow,
            approver=approver,
            action='FORWARD',
            step=workflow.current_step,
            comments=comments
        )

        # 2. Avançar para direção
        workflow.current_step = 'DIRECTOR_APPROVAL'
        workflow.requires_director_approval = True
        workflow.save()

        self.request.status = 'PENDING_DIRECTOR_APPROVAL'
        self.request.save()

        # 3. Notificar diretores
        self.notifications.notify_directors(self.request, comments)

        # 4. Limpar Assignments (Central de Compras encaminhou)
        self._clear_step_assignments(workflow.current_step, approver, 'COMPLETED')

        # 5. Criar Assignments para a direção (opcional, se Direção também usar a mesma caixa de entrada)
        # self._assign_to_group('Director', 'DIRECTOR_APPROVAL')

        logger.info(f"Request {self.request.id} forwarded to director")
        return approval

    @transaction.atomic
    def purchasing_edit(self, editor, changes_description):
        """
        Regista edição pela Central de Compras
        """
        logger.info(f"Purchasing edit on request {self.request.id} by {editor.username}")

        workflow = self.request.workflow

        # 1. Registar edição
        approval = Approval.objects.create(
            purchase_request=self.request,
            workflow=workflow,
            approver=editor,
            action='EDIT',
            step=workflow.current_step,
            comments=changes_description
        )

        # If changes_description is a JSON-serializable dict/list, store it in changes_json
        try:
            if isinstance(changes_description, (dict, list)):
                approval.changes_json = changes_description
                approval.save()
        except Exception:
            logger.debug('changes_description not JSON serializable')

        # 2. Atualizar campos de edição
        self.request.last_edited_by_purchasing_at = timezone.now()
        self.request.last_edited_by_purchasing_by = editor
        self.request.save()

        # 3. Notificar solicitante
        self.notifications.notify_purchasing_edit(self.request, editor)

        # 4. Após edição, re-analisar se precisa de direção e auto-encaminhar se configurado
        try:
            analysis = PurchasingAnalysisService(self.request)
            needs_director, reason = analysis.requires_director_approval()
            if needs_director and getattr(settings, 'AUTO_FORWARD_AFTER_EDIT', False):
                # auto forward
                self.forward_to_director(editor, f'Auto-forward after purchasing edit: {reason}')
        except Exception:
            logger.exception('Failed to auto-analyze after purchasing edit')

        logger.info(f"Purchasing edit recorded for request {self.request.id}")
        return approval

    # ----- MÉTODOS PRIVADOS -----

    def _get_initial_status(self):
        """Retorna status inicial baseado em quem preencheu"""
        if self.request.requested_by.approves_directly_to_purchasing():
            return 'PENDING_PURCHASING'

        if self.request.context_type == 'PROJECT':
            return 'PENDING_PROJECT_APPROVAL'
        else:
            return 'PENDING_DEPARTMENT_APPROVAL'

    def _setup_project_workflow(self, workflow):
        """Configura workflow para requisição de projeto"""
        workflow.requires_project_approval = True

        if self.request.requested_by.approves_directly_to_purchasing():
            # Team Leader, Responsável ou Coordenador -> direto para compras
            workflow.current_step = 'PURCHASING_ANALYSIS'
            self.request.status = 'PENDING_PURCHASING'
        else:
            # Administrativo -> precisa aprovação
            workflow.current_step = 'PROJECT_APPROVAL'
            self.request.status = 'PENDING_PROJECT_APPROVAL'

    def _setup_department_workflow(self, workflow):
        """Configura workflow para requisição departamental"""
        workflow.requires_department_approval = True

        if self.request.requested_by.approves_directly_to_purchasing():
            # Coordenador/Adjunto -> direto para compras
            workflow.current_step = 'PURCHASING_ANALYSIS'
            self.request.status = 'PENDING_PURCHASING'
        else:
            # Colaborador -> precisa aprovação
            workflow.current_step = 'DEPARTMENT_APPROVAL'
            self.request.status = 'PENDING_DEPARTMENT_APPROVAL'

    def _advance_workflow(self, workflow, approver):
        """Avança workflow para próximo passo"""

        # Se estava em aprovação de projeto/departamento
        if workflow.current_step in ['PROJECT_APPROVAL', 'DEPARTMENT_APPROVAL']:
            workflow.current_step = 'PURCHASING_ANALYSIS'
            self.request.status = 'PENDING_PURCHASING'
            workflow.save()
            self.request.save()

            # Notificar central de compras
            self.notifications.notify_purchasing_central(self.request)

        # Se estava em análise da central
        elif workflow.current_step == 'PURCHASING_ANALYSIS':
            analysis = PurchasingAnalysisService(self.request)
            precisa_direcao, motivo = analysis.requires_director_approval()

            if precisa_direcao:
                workflow.current_step = 'DIRECTOR_APPROVAL'
                workflow.requires_director_approval = True
                self.request.status = 'PENDING_DIRECTOR_APPROVAL'
                workflow.save()
                self.request.save()

                # Notificar diretores
                self.notifications.notify_directors(self.request, motivo)
            else:
                self._finalize_approval(workflow)

        # Se estava em aprovação da direção
        elif workflow.current_step == 'DIRECTOR_APPROVAL':
            self._finalize_approval(workflow)

    def _finalize_approval(self, workflow):
        """Finaliza workflow com sucesso"""
        workflow.current_step = 'APPROVED'
        workflow.completed_at = timezone.now()
        workflow.save()

        self.request.status = 'APPROVED'
        self.request.completed_at = timezone.now()
        # Marcar para sincronização com o ERP (mock)
        try:
            self.request.erp_sync_status = 'PENDING'
        except Exception:
            logger.debug('erp_sync_status field may not exist')
        self.request.save()

        # Notificar solicitante
        self.notifications.notify_requestor_approved(self.request)

    def _can_approve(self, user, current_step):
        """Verifica se user pode aprovar no passo atual"""

        if current_step == 'PROJECT_APPROVAL':
            # Qualquer membro dos grupos TeamLeader, ProjectResponsable, AdministrativeStaff
            if user.groups.filter(name__in=['TeamLeader', 'ProjectResponsable', 'AdministrativeStaff']).exists():
                return True
            # Ou se for explicitamente listado como aprovador do projeto
            possible_approvers = self.request.all_possible_approvers_for_project_request()
            return user in possible_approvers

        elif current_step == 'DEPARTMENT_APPROVAL':
            # Qualquer membro dos grupos Manager, DeputyManager
            if user.groups.filter(name__in=['Manager', 'DeputyManager']).exists():
                return True
            # Ou se fizer parte dos aprovadores do departamento
            return user in self.request.department.all_approvers

        elif current_step == 'PURCHASING_ANALYSIS':
            # Central de Compras (grupo)
            return user.groups.filter(name='PurchasingCentral').exists()

        elif current_step == 'DIRECTOR_APPROVAL':
            # Diretores e adjuntos
            return user.groups.filter(name__in=['Director', 'DeputyDirector']).exists()

        return False

    def _notify_next_approvers(self, workflow):
        """Notifica e aloca (assign) os próximos aprovadores"""

        if workflow.current_step == 'PROJECT_APPROVAL':
            approvers = self.request.all_possible_approvers_for_project_request()
            self._assign_approvers(workflow.current_step, approvers)
            self.notifications.notify_approvers(self.request, approvers, "Projeto")

        elif workflow.current_step == 'DEPARTMENT_APPROVAL':
            approvers = self.request.department.all_approvers
            self._assign_approvers(workflow.current_step, approvers)
            self.notifications.notify_approvers(self.request, approvers, "Departamento")

        elif workflow.current_step == 'PURCHASING_ANALYSIS':
            self.notifications.notify_purchasing_central(self.request)

    def _assign_approvers(self, step, approvers):
        """Cria os registos de Assignment para que a requisição apareça na inbox dos aprovadores"""
        # 1. Invalidar quaisquer assignments residuais em PENDING desta requisição (safety check)
        self.request.assignments.filter(status='PENDING').update(status='OBSOLETE')
        
        # 2. Criar novos
        assignments = []
        for approver in approvers:
            assignments.append(PurchaseRequestAssignment(
                purchase_request=self.request,
                approver=approver,
                step=step,
                status='PENDING'
            ))
        
        if assignments:
            PurchaseRequestAssignment.objects.bulk_create(assignments)

    def _clear_step_assignments(self, step, actor, actor_status='COMPLETED'):
        """Resolve as assignments da etapa atual. Quem tomou a ação fica com 'actor_status', os restantes com 'OBSOLETE'"""
        assignments = self.request.assignments.filter(status='PENDING') # Pode ser filtrado por step, ms PENDING global basta por PR
        
        for assignment in assignments:
            if assignment.approver == actor:
                assignment.status = actor_status
            else:
                assignment.status = 'OBSOLETE'
        
        PurchaseRequestAssignment.objects.bulk_update(assignments, ['status'])

    def bulk_process(self, actor, ids, action, comments="", reason=None):
        """
        Processa ações em lote pela Central de Compras.

        - actor: usuário que executa a ação (deve ser is_purchasing_central)
        - ids: lista de PurchaseRequest IDs
        - action: 'approve' | 'forward_to_director' | 'reject'
        - comments/reason: opcionais (reason obrigatório para reject)

        Comportamento: per-request atomic (cada requisição é processada em sua própria transação),
        retornando listas de sucesso e falha.
        """
        from django.db import transaction
        from ..models import PurchaseRequest

        results = {
            'success': [],
            'failed': []
        }

        if not actor.is_purchasing_central:
            raise PermissionError('Apenas Central de Compras pode executar ações em lote')

        if action == 'reject' and not reason:
            raise ValueError('Reason is required for bulk reject')

        for req_id in ids:
            try:
                with transaction.atomic():
                    purchase_request = PurchaseRequest.objects.select_for_update().get(id=req_id)

                    # Only allow processing when in purchasing pending or appropriate step
                    wf = purchase_request.workflow
                    # Define allowed statuses/steps for central bulk actions
                    allowed_statuses = ['PENDING_PURCHASING', 'PENDING_DIRECTOR_APPROVAL']
                    allowed_steps = ['PURCHASING_ANALYSIS']

                    # Allow processing when the purchase_request.status indicates it's at purchasing,
                    # even if the workflow.current_step hasn't been synced yet (e.g., created directly in tests).
                    if purchase_request.status not in allowed_statuses and wf.current_step not in allowed_steps:
                        raise ValueError(
                            f'Request {req_id} not in purchasing step (status: {purchase_request.status}, step: {wf.current_step})'
                        )

                    # If status indicates PENDING_PURCHASING but workflow step isn't set, sync it to PURCHASING_ANALYSIS
                    if purchase_request.status == 'PENDING_PURCHASING' and wf.current_step not in allowed_steps:
                        wf.current_step = 'PURCHASING_ANALYSIS'
                        wf.save()

                    # Dispatch action
                    if action == 'approve':
                        self.request = purchase_request
                        self.approve(actor, comments)
                    elif action == 'forward_to_director':
                        self.request = purchase_request
                        self.forward_to_director(actor, comments)
                    elif action == 'reject':
                        self.request = purchase_request
                        self.reject(actor, reason)
                    else:
                        raise ValueError('Invalid action')

                    results['success'].append(req_id)
            except Exception as e:
                logger.exception(f"Bulk action failed for request {req_id}: {str(e)}")
                results['failed'].append({'id': req_id, 'error': str(e)})

        # Pós-processamento: enviar notificações em lote para central / solicitantes
        try:
            # Carregar objetos para notificações
            processed_requests = PurchaseRequest.objects.filter(id__in=results['success'])
            self.notifications.notify_batch(processed_requests, action, actor, comments=comments, reason=reason)
        except Exception:
            logger.exception('Failed to send batch notifications')

        return results
