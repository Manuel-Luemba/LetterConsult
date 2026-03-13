from django.test import TestCase

# Create your tests here.
import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from core.timesheet.models import Timesheet


@pytest.mark.django_db
def test_my_timesheets_authenticated():
    user = User.objects.create_user(username='manuel', password='1234')
    client = APIClient()
    client.login(username='manuel', password='1234')

    # Criar timesheets de exemplo
    Timesheet.objects.create(employee=user, date_joined='2025-09-01')
    Timesheet.objects.create(employee=user, date_joined='2025-09-02')

    response = client.get("/api/timesheets/my")
    assert response.status_code == 200
    assert len(response.data['items']) == 2
    assert 'status' in response.data['items'][0]
    assert 'tasks_count' in response.data['items'][0]

@pytest.mark.django_db
def test_my_timesheets_unauthenticated():
    client = APIClient()
    response = client.get("/api/timesheets/my")
    assert response.status_code == 401  # ou 403 dependendo da configuração
