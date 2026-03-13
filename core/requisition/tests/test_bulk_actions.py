import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'app.settings')
import django
django.setup()

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from core.requisition.models import PurchaseRequest, ApprovalWorkflow
from core.requisition.services.workflow_service import WorkflowService
from decimal import Decimal
from django.utils import timezone
from core.erp.models import Department

User = get_user_model()

class BulkActionsTestCase(TestCase):
    def setUp(self):
        # Criar grupo PurchasingCentral
        self.p_group, _ = Group.objects.get_or_create(name='PurchasingCentral')

        # Usuários
        self.purchasing_user = User.objects.create_user(username='purch', password='pass')
        self.purchasing_user.groups.add(self.p_group)

        self.other_user = User.objects.create_user(username='other', password='pass')

        # Criar departamento obrigatório
        self.dept = Department.objects.create(name='Dept A', abbreviation='DA')

        # Criar duas requisições
        self.pr1 = PurchaseRequest.objects.create(
            context_type='DEPARTMENT',
            department=self.dept,
            requested_by=self.other_user,
            required_date=timezone.now().date(),
            reference_month=timezone.now().date(),
            justification='Teste',
            observations='',
            status='PENDING_PURCHASING',
            total_amount=Decimal('100.00')
        )
        self.pr2 = PurchaseRequest.objects.create(
            context_type='DEPARTMENT',
            department=self.dept,
            requested_by=self.other_user,
            required_date=timezone.now().date(),
            reference_month=timezone.now().date(),
            justification='Teste 2',
            observations='',
            status='PENDING_PURCHASING',
            total_amount=Decimal('200.00')
        )

        # Garantir workflow criado
        ApprovalWorkflow.objects.get_or_create(purchase_request=self.pr1)
        ApprovalWorkflow.objects.get_or_create(purchase_request=self.pr2)

    def test_bulk_approve_success(self):
        service = WorkflowService(None)
        results = service.bulk_process(self.purchasing_user, [self.pr1.id, self.pr2.id], 'approve', comments='Batch approve')
        self.assertEqual(len(results['success']), 2)
        self.pr1.refresh_from_db()
        self.pr2.refresh_from_db()
        self.assertEqual(self.pr1.status, 'APPROVED')
        self.assertEqual(self.pr2.status, 'APPROVED')

    def test_bulk_permission_denied(self):
        service = WorkflowService(None)
        with self.assertRaises(PermissionError):
            service.bulk_process(self.other_user, [self.pr1.id], 'approve')

    def test_bulk_reject_requires_reason(self):
        service = WorkflowService(None)
        with self.assertRaises(ValueError):
            service.bulk_process(self.purchasing_user, [self.pr1.id], 'reject')
