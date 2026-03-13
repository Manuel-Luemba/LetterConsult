import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'app.settings')
django.setup()

from django.test import RequestFactory
from core.requisition.models import PurchaseRequest
from core.user.models import User
from crum import impersonate
from core.requisition.schemas import PurchaseRequestSchema
from core.requisition.api import list_purchase_requests

def test_list():
    factory = RequestFactory()
    request = factory.get('/api/v1/requisitions/list?tab=all&assigned_to_me=false&is_urgent=false&overdue=false&edited_by_purchasing=false&page=1&page_size=20')
    
    user = User.objects.filter(is_superuser=True).first()
    request.user = user
    request.auth = user

    with impersonate(user):
        import ninja
        from ninja.pagination import PageNumberPagination
        paginator = PageNumberPagination(page_size=20)
        qs = PurchaseRequest.objects.all().order_by('-created_at')
        
        # This is exactly what Ninja's decorator does
        from ninja.schema import NinjaModel
        items = list(qs[:2])
        print("Got 2 items. Constructing Schema...")
        try:
            # Emulate Ninja Schema parsing for the list
            # Ninja usually uses Resolver to evaluate everything
            res = [PurchaseRequestSchema.from_orm(i).dict() for i in items]
            print("Mapped OK!")
        except BaseException as e:
            print("ERROR mapping:")
            print(str(e))

if __name__ == '__main__':
    test_list()
