import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'app.settings')
django.setup()

from django.test import RequestFactory
from core.requisition.models import PurchaseRequest
from core.user.models import User
from crum import impersonate

def test_list():
    factory = RequestFactory()
    request = factory.get('/api/v1/requisitions/list')
    
    user = User.objects.filter(is_superuser=True).first()
    if not user:
        user = User.objects.filter(is_active=True).first()
    request.user = user
    request.auth = user

    with impersonate(user):
        qs = PurchaseRequest.objects.all()
        print("QuerySet count:", qs.count())
        
        from core.requisition.schemas import PurchaseRequestSchema
        for req in qs[:5]:
            print(f"\nProcessing PR id={req.id}")
            try:
                schema = PurchaseRequestSchema.from_orm(req)
                print("Mapped successfully! Code:", schema.code)
            except Exception as e:
                print("ERROR mapping PR:", req.id)
                import traceback
                traceback.print_exc()

if __name__ == '__main__':
    test_list()
