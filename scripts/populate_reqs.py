# Script de população de requisições para ambiente de desenvolvimento
# Execute via: python manage.py shell < scripts/populate_reqs.py

from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from core.requisition.models import PurchaseRequest, PurchaseRequestItem, ApprovalWorkflow
from core.erp.models import Department
from django.db import transaction

User = get_user_model()

# Config
USER_ID = 1
NUM_REQUESTS = 10

user = User.objects.filter(id=USER_ID).first()
if not user:
    print(f"User with id={USER_ID} not found. Please create user before running this script.")
    raise SystemExit(1)

# Ensure there's at least one department
dept = Department.objects.first()
if not dept:
    dept = Department.objects.create(name='Default Department', abbreviation='DEF')
    print(f"Created department id={dept.id}")

created_ids = []

for i in range(1, NUM_REQUESTS + 1):
    with transaction.atomic():
        pr = PurchaseRequest.objects.create(
            context_type='DEPARTMENT',
            department=dept,
            requested_by=user,
            required_date=date.today() + timedelta(days=7 + i),
            reference_month=date.today().replace(day=1),
            justification=f'Test requisition {i}',
            observations='Auto-generated for tests',
            status='DRAFT'
        )

        # create or get workflow
        wf, _ = ApprovalWorkflow.objects.get_or_create(purchase_request=pr)

        # create items: mix of priced and unpriced
        num_items = 1 if i % 3 == 0 else 2
        for j in range(1, num_items + 1):
            # alternate priced and unpriced
            if (i + j) % 2 == 0:
                unit_price = Decimal('1000.00') * j
            else:
                unit_price = None

            item = PurchaseRequestItem.objects.create(
                purchase_request=pr,
                description=f'Item {j} for PR {pr.id}',
                urgency_level='LOW',
                quantity=1,
                unit_price=unit_price,
                observations=''
            )

        # set submitted status to PENDING_PURCHASING for half of them
        if i <= NUM_REQUESTS // 2:
            pr.status = 'PENDING_PURCHASING'
            pr.submitted_at = None
            pr.save()

        created_ids.append(pr.id)

print(f"Created {len(created_ids)} PurchaseRequests: {created_ids}")
print('Done')

