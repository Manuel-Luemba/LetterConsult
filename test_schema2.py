import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'app.settings')
django.setup()

from django.test import RequestFactory
from core.requisition.models import PurchaseRequest
from core.user.models import User
from crum import impersonate
from ninja.pagination import PageNumberPagination
from ninja import Router, Schema
from typing import List
from core.requisition.schemas import PurchaseRequestSchema

class NinjaResponseSchema(Schema):
    count: int
    items: List[PurchaseRequestSchema]

def test_list():
    factory = RequestFactory()
    request = factory.get('/api/v1/requisitions/list')
    
    # Simulate AnonymousUser or a user
    user = User.objects.filter(is_superuser=True).first()
    request.user = user
    request.auth = user

    with impersonate(user):
        qs = PurchaseRequest.objects.all()[:2]
        data = {"count": 2, "items": list(qs)}
        print("Validating NinjaResponseSchema with count and items...")
        try:
            schema = NinjaResponseSchema.from_orm(data)
            print("Mapped successfully!")
        except Exception as e:
            print("ERROR:")
            print(str(e))
            import traceback
            traceback.print_exc()

if __name__ == '__main__':
    test_list()
