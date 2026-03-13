
import os
import django
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'app.settings')
django.setup()

User = get_user_model()

print("--- USERS ---")
for user in User.objects.all():
    groups = ", ".join([g.name for g in user.groups.all()])
    print(f"User: {user.username} | Email: {user.email} | Groups: [{groups}] | is_active: {user.is_active}")

print("\n--- GROUPS ---")
for group in Group.objects.all():
    member_count = group.user_set.count()
    print(f"Group: {group.name} | Members: {member_count}")

print("\n--- EMAIL SETTINGS ---")
print(f"DEFAULT_FROM_EMAIL: {settings.DEFAULT_FROM_EMAIL}")
print(f"EMAIL_BACKEND: {settings.EMAIL_BACKEND}")
