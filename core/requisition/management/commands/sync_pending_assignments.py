from django.core.management.base import BaseCommand
from core.requisition.models import PurchaseRequest, PurchaseRequestAssignment

class Command(BaseCommand):
    help = 'Gera e sincroniza retroativamente as Assignments para as Requisições de Compra Pendentes de departamentos e projetos.'

    def handle(self, *args, **options):
        # 1. Requisições pendentes de aprovação de PROJETO
        project_requests = PurchaseRequest.objects.filter(status='PENDING_PROJECT_APPROVAL')
        assigned_project_count = 0

        for pr in project_requests:
            approvers = pr.all_possible_approvers_for_project_request()
            for approver in approvers:
                assignment, created = PurchaseRequestAssignment.objects.get_or_create(
                    purchase_request=pr,
                    approver=approver,
                    step='PROJECT_APPROVAL',
                    defaults={'status': 'PENDING'}
                )
                if created:
                    assigned_project_count += 1
            
            # Garantir que invalidamos o que está desnecessário caso hierarquias tenham mudado no passado
            approver_ids = [a.id for a in approvers]
            pr.assignments.exclude(approver_id__in=approver_ids).filter(status='PENDING').update(status='OBSOLETE')
                
        self.stdout.write(self.style.SUCCESS(f'Successfully assigned {assigned_project_count} new tasks for pending PROJECT requests.'))

        # 2. Requisições pendentes de aprovação de DEPARTAMENTO
        department_requests = PurchaseRequest.objects.filter(status='PENDING_DEPARTMENT_APPROVAL')
        assigned_dept_count = 0

        for pr in department_requests:
            if pr.department:
                approvers = pr.department.all_approvers
                for approver in approvers:
                    assignment, created = PurchaseRequestAssignment.objects.get_or_create(
                        purchase_request=pr,
                        approver=approver,
                        step='DEPARTMENT_APPROVAL',
                        defaults={'status': 'PENDING'}
                    )
                    if created:
                        assigned_dept_count += 1

                approver_ids = [a.id for a in approvers]
                pr.assignments.exclude(approver_id__in=approver_ids).filter(status='PENDING').update(status='OBSOLETE')

        self.stdout.write(self.style.SUCCESS(f'Successfully assigned {assigned_dept_count} new tasks for pending DEPARTMENT requests.'))
        self.stdout.write(self.style.SUCCESS('All pending purchase requests are now fully synchronized with the Inbox models!'))
