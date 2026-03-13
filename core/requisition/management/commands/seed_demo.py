from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.utils import timezone
from decimal import Decimal

from core.erp.models import Department
from core.requisition.models import PurchaseRequest, PurchaseRequestItem, ApprovalWorkflow

User = get_user_model()


class Command(BaseCommand):
    help = 'Seed demo data: groups, users, department and sample purchase requests.'

    def handle(self, *args, **options):
        self.stdout.write('Seeding demo data...')

        # 1) Ensure groups exist
        group_names = [
            'Administrator', 'Manager', 'RH', 'Collaborator', 'Director', 'Logistics',
            'TeamLeader', 'ProjectResponsable', 'AdministrativeStaff', 'DeputyManager',
            'PurchasingCentral', 'DeputyDirector'
        ]
        groups = {}
        for g in group_names:
            group, created = Group.objects.get_or_create(name=g)
            groups[g] = group
            if created:
                self.stdout.write(f'  Created group: {g}')

        # 2) Create users
        users_def = [
            ('purchasing', 'purchasing@demo.local', 'Purchasing User', ['PurchasingCentral']),
            ('alice', 'alice@demo.local', 'Alice Demo', ['Collaborator']),
            ('bob', 'bob@demo.local', 'Bob Manager', ['Manager']),
            ('director', 'director@demo.local', 'Director Demo', ['Director']),
        ]

        users = {}
        for username, email, full_name, user_groups in users_def:
            user, created = User.objects.get_or_create(username=username, defaults={'email': email})
            if created:
                user.set_password('pass')
                # Try to set first/last name if fields exist
                try:
                    user.first_name = full_name.split()[0]
                    user.last_name = ' '.join(full_name.split()[1:])
                except Exception:
                    pass
                user.save()
                self.stdout.write(f'  Created user: {username} (password: pass)')
            else:
                self.stdout.write(f'  User exists: {username}')

            # Add to groups
            for g in user_groups:
                grp = groups.get(g)
                if grp and not user.groups.filter(name=g).exists():
                    user.groups.add(grp)
            users[username] = user

        # 3) Create a demo department
        dept, created = Department.objects.get_or_create(name='Dept Demo', defaults={'abbreviation': 'DD'})
        if created:
            self.stdout.write('  Created Department: Dept Demo')
        else:
            self.stdout.write('  Department exists: Dept Demo')

        # 4) Create sample purchase requests (idempotent)
        seed_marker = 'SEED-DEMO'
        existing = PurchaseRequest.objects.filter(justification__icontains=seed_marker)
        if existing.exists():
            self.stdout.write(f'  Found {existing.count()} existing seeded purchase requests; skipping creation')
        else:
            prs = []
            now = timezone.now()

            pr1 = PurchaseRequest.objects.create(
                context_type='DEPARTMENT',
                department=dept,
                requested_by=users['alice'],
                required_date=now.date(),
                reference_month=now.date(),
                justification=f'Seed demo PR 1 {seed_marker}',
                observations='Demo purchase request 1',
                status='PENDING_PURCHASING',
                total_amount=Decimal('100.00')
            )
            PurchaseRequestItem.objects.create(
                purchase_request=pr1,
                description='Demo Item 1',
                urgency_level='LOW',
                quantity=Decimal('1'),
                unit_price=Decimal('100.00'),
                special_status='NORMAL',
                observations='',
                delivery_deadline=now.date(),
            )
            ApprovalWorkflow.objects.get_or_create(purchase_request=pr1, defaults={'current_step': 'PURCHASING_ANALYSIS'})
            prs.append(pr1)

            pr2 = PurchaseRequest.objects.create(
                context_type='DEPARTMENT',
                department=dept,
                requested_by=users['alice'],
                required_date=now.date(),
                reference_month=now.date(),
                justification=f'Seed demo PR 2 {seed_marker}',
                observations='Demo purchase request 2',
                status='PENDING_PURCHASING',
                total_amount=Decimal('2000000.00')
            )
            PurchaseRequestItem.objects.create(
                purchase_request=pr2,
                description='Demo Item 2',
                urgency_level='HIGH',
                quantity=Decimal('10'),
                unit_price=Decimal('200000.00'),
                special_status='NORMAL',
                observations='',
                delivery_deadline=now.date(),
            )
            ApprovalWorkflow.objects.get_or_create(purchase_request=pr2, defaults={'current_step': 'PURCHASING_ANALYSIS'})
            prs.append(pr2)

            self.stdout.write(f'  Created {len(prs)} purchase requests')

        # 5) Summary
        total_pr = PurchaseRequest.objects.count()
        total_users = User.objects.count()
        total_groups = Group.objects.count()

        self.stdout.write('\nSeed complete:')
        self.stdout.write(f'  Users total: {total_users}')
        self.stdout.write(f'  Groups total: {total_groups}')
        self.stdout.write(f'  PurchaseRequests total: {total_pr}')
        self.stdout.write('Done')

