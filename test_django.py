import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'app.settings')
django.setup()

from django.test import RequestFactory
from core.requisition.models import PurchaseRequest
from django.contrib.auth.models import AnonymousUser
from crum import impersonate

def test_django_error():
    factory = RequestFactory()
    request = factory.get('/')
    request.user = AnonymousUser()

    with impersonate(request.user):
        pr = PurchaseRequest.objects.first()
        try:
            print("Trying to exclude by AnonymousUser...")
            qs = pr.assignments.filter(status='PENDING').exclude(approver=request.user)
            print("Count:", qs.count())
            print("Success!")
        except Exception as e:
            print("ERROR CAUGHT:")
            import traceback
            traceback.print_exc()

if __name__ == '__main__':
    test_django_error()
