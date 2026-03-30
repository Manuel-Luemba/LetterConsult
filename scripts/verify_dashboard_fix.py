import os
import django
import sys

# Setup Django
sys.path.append('c:\\projeto\\LetterConsult')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LetterConsult.settings')
django.setup()

from core.requisition.models import PurchaseRequest, Approval
from django.contrib.auth.models import User
from decimal import Decimal

def test_dashboard_stats():
    print("--- Testing Dashboard Stats & Counts ---")
    
    # Get a manager user (e.g., jaime.kayembe)
    try:
        user = User.objects.get(username='jaime.kayembe')
        print(f"User: {user.username}")
    except User.DoesNotExist:
        print("User jaime.kayembe not found. Using first user in Managers group.")
        user = User.objects.filter(groups__name='Managers').first()
        if not user:
            print("No manager found.")
            return

    # Check Dashboard Stats
    from core.requisition.api import get_dashboard_stats
    
    class MockRequest:
        def __init__(self, user):
            self.auth = user
            self.GET = {}

    req = MockRequest(user)
    stats = get_dashboard_stats(req)
    
    manager_stats = stats.get('manager', {})
    print(f"Manager Approved Total: {manager_stats.get('approved_total_amount')}")
    print(f"Manager Approved Count: {manager_stats.get('approved_by_me_count')}")
    
    # Check Counts by Status (Requester Context)
    from core.requisition.api import get_counts_by_status
    
    counts_req = get_counts_by_status(req, role_context='requester')
    print(f"Requester Counts: {counts_req}")
    
    # Check Counts by Status (Approver Context)
    counts_app = get_counts_by_status(req, role_context='approver')
    print(f"Approver Counts: {counts_app}")

if __name__ == "__main__":
    test_dashboard_stats()
