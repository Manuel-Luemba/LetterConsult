from django.test import TestCase
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from core.requisition.models import PurchaseRequest, PurchaseRequestItem, ApprovalWorkflow
from core.requisition.services.PurchasingAnalysisService import PurchasingAnalysisService
from core.requisition.services.workflow_service import WorkflowService
from core.erp.models import Department
from decimal import Decimal
from datetime import date, timedelta

User = get_user_model()


class PurchasingAnalysisTests(TestCase):
    def setUp(self):
        # Create groups
        Group.objects.get_or_create(name='PurchasingCentral')

        # Create user and assign to PurchasingCentral
        self.user = User.objects.create(username='pcentral', first_name='Purchasing', last_name='Central')
        g = Group.objects.get(name='PurchasingCentral')
        self.user.groups.add(g)

        # Create department and PR
        self.dept = Department.objects.create(name='Dept Test', abbreviation='DT')

        self.pr = PurchaseRequest.objects.create(
            context_type='DEPARTMENT',
            department=self.dept,
            requested_by=self.user,
            required_date=date.today() + timedelta(days=7),
            reference_month=date.today().replace(day=1),
            justification='Test',
            observations='',
            status='PENDING_PURCHASING'
        )
        ApprovalWorkflow.objects.get_or_create(purchase_request=self.pr)

    def test_analyze_returns_missing_items(self):
        # Create items: one with no price and no supplier, one with price only
        item1 = PurchaseRequestItem.objects.create(
            purchase_request=self.pr,
            description='Item 1',
            urgency_level='LOW',
            quantity=1,
            unit_price=None,
            preferred_supplier=None
        )
        item2 = PurchaseRequestItem.objects.create(
            purchase_request=self.pr,
            description='Item 2',
            urgency_level='LOW',
            quantity=2,
            unit_price=Decimal('100.00'),
            preferred_supplier=None
        )

        analysis = PurchasingAnalysisService(self.pr).analyze_request()
        self.assertIn('items_missing_details', analysis)
        missing = analysis['items_missing_details']
        # Expect two entries: item1 missing price+supplier, item2 missing supplier
        self.assertEqual(len(missing), 2)
        m1 = next((m for m in missing if m['item_id'] == item1.id), None)
        m2 = next((m for m in missing if m['item_id'] == item2.id), None)
        self.assertIsNotNone(m1)
        self.assertIsNotNone(m2)
        self.assertIn('price', m1['missing'])
        self.assertIn('supplier', m1['missing'])
        self.assertIn('supplier', m2['missing'])

    def test_workflow_approve_blocks_when_missing(self):
        # Create item without supplier/price
        item = PurchaseRequestItem.objects.create(
            purchase_request=self.pr,
            description='Item X',
            urgency_level='LOW',
            quantity=1,
            unit_price=None,
            preferred_supplier=None
        )

        svc = WorkflowService(self.pr)
        # user is in PurchasingCentral group
        with self.assertRaises(Exception) as cm:
            svc.approve(self.user, 'Trying to approve')
        self.assertTrue('sem preço' in str(cm.exception) or 'fornecedor' in str(cm.exception) or 'sem' in str(cm.exception))

