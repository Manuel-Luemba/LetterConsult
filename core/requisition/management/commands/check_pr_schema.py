from django.core.management.base import BaseCommand
from core.requisition.models import PurchaseRequest
from core.requisition.schemas import PurchaseRequestSchema


class Command(BaseCommand):
    help = 'Check PurchaseRequestSchema conversion for all PRs'

    def handle(self, *args, **options):
        prs = list(PurchaseRequest.objects.all())
        self.stdout.write(f'PR count: {len(prs)}')
        for pr in prs:
            try:
                s = PurchaseRequestSchema.from_orm(pr)
                self.stdout.write(f'OK {pr.id} is_urgent={s.is_urgent} can_approve={s.can_current_user_approve}')
            except Exception as e:
                self.stdout.write(f'ERROR {pr.id} -> {e}')

