# management/commands/setup_groups.py
from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.apps import apps



class Command(BaseCommand):
    help = 'Setup groups and permissions for Purchase Request System'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Creating groups and permissions...'))

        # ============================================
        # 1. DEFINIR GRUPOS
        # ============================================
        groups = {
            # CARGO GROUPS (baseados nos existentes)
            'Collaborator': 'COLABORADOR - Regular employee',
            'Manager': 'GESTOR - Department manager/coordinator',
            'Director': 'DIRECTOR - Board member',
            'Administrator': 'ADMINISTRADOR - System administrator',
            'HR': 'RH - Human Resources department',
            'Logistics': 'LOGISTICO - Logistics department',

            # FUNÇÃO NO PROJETO
            'TeamLeader': 'Team leader of a project',
            'ProjectResponsable': 'Project responsible',
            'AdministrativeStaff': 'Administrative staff allocated to project',

            # FUNÇÃO NO DEPARTAMENTO
            'DeputyCoordinator': 'Deputy department coordinator',

            # UNIDADES ESPECÍFICAS
            'PurchasingCentral': 'Purchasing central analyst',
            'DeputyDirector': 'Deputy director',
        }

        created_groups = {}
        for group_name, description in groups.items():
            group, created = Group.objects.get_or_create(name=group_name)
            created_groups[group_name] = group
            if created:
                self.stdout.write(f'  ✓ Created group: {group_name}')
            else:
                self.stdout.write(f'  ✓ Group already exists: {group_name}')

        # ============================================
        # 2. OBTER CONTENT TYPES
        # ============================================
        PurchaseRequest = apps.get_model('purchases', 'PurchaseRequest')
        PurchaseRequestItem = apps.get_model('purchases', 'PurchaseRequestItem')
        ApprovalWorkflow = apps.get_model('purchases', 'ApprovalWorkflow')
        Approval = apps.get_model('purchases', 'Approval')
        Attachment = apps.get_model('purchases', 'Attachment')
        Project = apps.get_model('projects', 'Project')
        Department = apps.get_model('departments', 'Department')

        ct_pr = ContentType.objects.get_for_model(PurchaseRequest)
        ct_item = ContentType.objects.get_for_model(PurchaseRequestItem)
        ct_wf = ContentType.objects.get_for_model(ApprovalWorkflow)
        ct_app = ContentType.objects.get_for_model(Approval)
        ct_att = ContentType.objects.get_for_model(Attachment)
        ct_project = ContentType.objects.get_for_model(Project)
        ct_dept = ContentType.objects.get_for_model(Department)

        # ============================================
        # 3. CRIAR/OBTER PERMISSÕES
        # ============================================

        # PurchaseRequest Permissions
        pr_permissions = {
            'view_purchaserequest': Permission.objects.get_or_create(
                codename='view_purchaserequest',
                content_type=ct_pr,
                name='Can view purchase request'
            )[0],
            'add_purchaserequest': Permission.objects.get_or_create(
                codename='add_purchaserequest',
                content_type=ct_pr,
                name='Can add purchase request'
            )[0],
            'change_purchaserequest': Permission.objects.get_or_create(
                codename='change_purchaserequest',
                content_type=ct_pr,
                name='Can change purchase request'
            )[0],
            'delete_purchaserequest': Permission.objects.get_or_create(
                codename='delete_purchaserequest',
                content_type=ct_pr,
                name='Can delete purchase request'
            )[0],
            'approve_purchaserequest_department': Permission.objects.get_or_create(
                codename='approve_purchaserequest_department',
                content_type=ct_pr,
                name='Can approve purchase request (department/project level)'
            )[0],
            'approve_purchaserequest_purchasing': Permission.objects.get_or_create(
                codename='approve_purchaserequest_purchasing',
                content_type=ct_pr,
                name='Can approve purchase request (purchasing level)'
            )[0],
            'approve_purchaserequest_director': Permission.objects.get_or_create(
                codename='approve_purchaserequest_director',
                content_type=ct_pr,
                name='Can approve purchase request (director level)'
            )[0],
            'reject_purchaserequest': Permission.objects.get_or_create(
                codename='reject_purchaserequest',
                content_type=ct_pr,
                name='Can reject purchase request'
            )[0],
            'edit_purchaserequest_purchasing': Permission.objects.get_or_create(
                codename='edit_purchaserequest_purchasing',
                content_type=ct_pr,
                name='Can edit purchase request (purchasing level)'
            )[0],
        }

        # Project Permissions
        project_permissions = {
            'view_project': Permission.objects.get_or_create(
                codename='view_project',
                content_type=ct_project,
                name='Can view project'
            )[0],
            'add_project': Permission.objects.get_or_create(
                codename='add_project',
                content_type=ct_project,
                name='Can add project'
            )[0],
            'change_project': Permission.objects.get_or_create(
                codename='change_project',
                content_type=ct_project,
                name='Can change project'
            )[0],
            'assign_project_responsables': Permission.objects.get_or_create(
                codename='assign_project_responsables',
                content_type=ct_project,
                name='Can assign project responsables'
            )[0],
            'assign_project_teamleader': Permission.objects.get_or_create(
                codename='assign_project_teamleader',
                content_type=ct_project,
                name='Can assign project team leader'
            )[0],
            'assign_project_administrative': Permission.objects.get_or_create(
                codename='assign_project_administrative',
                content_type=ct_project,
                name='Can assign project administrative staff'
            )[0],
        }

        # Department Permissions
        dept_permissions = {
            'view_department': Permission.objects.get_or_create(
                codename='view_department',
                content_type=ct_dept,
                name='Can view department'
            )[0],
            'change_department': Permission.objects.get_or_create(
                codename='change_department',
                content_type=ct_dept,
                name='Can change department'
            )[0],
            'assign_department_coordinators': Permission.objects.get_or_create(
                codename='assign_department_coordinators',
                content_type=ct_dept,
                name='Can assign department coordinators'
            )[0],
            'assign_department_deputies': Permission.objects.get_or_create(
                codename='assign_department_deputies',
                content_type=ct_dept,
                name='Can assign department deputy coordinators'
            )[0],
        }

        # Item Permissions (básicas)
        item_permissions = {
            'view_purchaserequestitem': Permission.objects.get_or_create(
                codename='view_purchaserequestitem',
                content_type=ct_item,
                name='Can view purchase request item'
            )[0],
            'add_purchaserequestitem': Permission.objects.get_or_create(
                codename='add_purchaserequestitem',
                content_type=ct_item,
                name='Can add purchase request item'
            )[0],
            'change_purchaserequestitem': Permission.objects.get_or_create(
                codename='change_purchaserequestitem',
                content_type=ct_item,
                name='Can change purchase request item'
            )[0],
        }

        # Workflow Permissions
        workflow_permissions = {
            'view_approvalworkflow': Permission.objects.get_or_create(
                codename='view_approvalworkflow',
                content_type=ct_wf,
                name='Can view approval workflow'
            )[0],
        }

        # Approval Permissions
        approval_permissions = {
            'view_approval': Permission.objects.get_or_create(
                codename='view_approval',
                content_type=ct_app,
                name='Can view approval'
            )[0],
        }

        # Attachment Permissions
        attachment_permissions = {
            'view_attachment': Permission.objects.get_or_create(
                codename='view_attachment',
                content_type=ct_att,
                name='Can view attachment'
            )[0],
            'add_attachment': Permission.objects.get_or_create(
                codename='add_attachment',
                content_type=ct_att,
                name='Can add attachment'
            )[0],
            'delete_attachment': Permission.objects.get_or_create(
                codename='delete_attachment',
                content_type=ct_att,
                name='Can delete attachment'
            )[0],
        }

        # ============================================
        # 4. ATRIBUIR PERMISSÕES AOS GRUPOS
        # ============================================

        # ----- Collaborator (COLABORADOR) -----
        collab = created_groups['Collaborator']
        collab.permissions.add(
            pr_permissions['view_purchaserequest'],
            pr_permissions['add_purchaserequest'],
            pr_permissions['change_purchaserequest'],
            item_permissions['view_purchaserequestitem'],
            item_permissions['add_purchaserequestitem'],
            item_permissions['change_purchaserequestitem'],
            project_permissions['view_project'],
            dept_permissions['view_department'],
            workflow_permissions['view_approvalworkflow'],
            approval_permissions['view_approval'],
            # attachment_permissions['view_attachment'],
            # attachment_permissions['add_attachment'],
        )
        self.stdout.write('  ✓ Collaborator permissions set')

        # ----- Manager (GESTOR) -----
        manager = created_groups['Manager']
        manager.permissions.add(
            # PurchaseRequest
            pr_permissions['view_purchaserequest'],
            pr_permissions['add_purchaserequest'],
            pr_permissions['change_purchaserequest'],
            pr_permissions['approve_purchaserequest_department'],
            pr_permissions['reject_purchaserequest'],
            # Items
            item_permissions['view_purchaserequestitem'],
            item_permissions['add_purchaserequestitem'],
            item_permissions['change_purchaserequestitem'],
            # Project
            project_permissions['view_project'],
            project_permissions['add_project'],
            project_permissions['change_project'],
            project_permissions['assign_project_responsables'],
            project_permissions['assign_project_teamleader'],
            project_permissions['assign_project_administrative'],
            # Department
            dept_permissions['view_department'],
            dept_permissions['change_department'],
            dept_permissions['assign_department_coordinators'],
            dept_permissions['assign_department_deputies'],
            # Workflow & Approvals
            workflow_permissions['view_approvalworkflow'],
            approval_permissions['view_approval'],
            # Attachments
            # attachment_permissions['view_attachment'],
            # attachment_permissions['add_attachment'],
        )
        self.stdout.write('  ✓ Manager permissions set')

        # ----- Director (DIRECTOR) -----
        director = created_groups['Director']
        director.permissions.add(
            pr_permissions['view_purchaserequest'],
            pr_permissions['approve_purchaserequest_director'],
            pr_permissions['reject_purchaserequest'],
            project_permissions['view_project'],
            dept_permissions['view_department'],
            workflow_permissions['view_approvalworkflow'],
            approval_permissions['view_approval'],
            # attachment_permissions['view_attachment'],
        )
        self.stdout.write('  ✓ Director permissions set')

        # ----- DeputyDirector -----
        deputy_dir = created_groups['DeputyDirector']
        deputy_dir.permissions.add(
            pr_permissions['view_purchaserequest'],
            pr_permissions['approve_purchaserequest_director'],
            pr_permissions['reject_purchaserequest'],
            project_permissions['view_project'],
            dept_permissions['view_department'],
            workflow_permissions['view_approvalworkflow'],
            approval_permissions['view_approval'],
        )
        self.stdout.write('  ✓ DeputyDirector permissions set')

        # ----- Administrator (ADMINISTRADOR) -----
        admin = created_groups['Administrator']
        all_permissions = Permission.objects.all()
        admin.permissions.set(all_permissions)
        self.stdout.write('  ✓ Administrator permissions set (all permissions)')

        # ----- TeamLeader -----
        tl = created_groups['TeamLeader']
        tl.permissions.add(
            pr_permissions['view_purchaserequest'],
            pr_permissions['add_purchaserequest'],
            pr_permissions['change_purchaserequest'],
            pr_permissions['approve_purchaserequest_department'],
            pr_permissions['reject_purchaserequest'],
            item_permissions['view_purchaserequestitem'],
            item_permissions['add_purchaserequestitem'],
            item_permissions['change_purchaserequestitem'],
            project_permissions['view_project'],
            dept_permissions['view_department'],
            workflow_permissions['view_approvalworkflow'],
            approval_permissions['view_approval'],
            # attachment_permissions['view_attachment'],
            # attachment_permissions['add_attachment'],
        )
        self.stdout.write('  ✓ TeamLeader permissions set')

        # ----- ProjectResponsable -----
        pr_resp = created_groups['ProjectResponsable']
        pr_resp.permissions.add(
            pr_permissions['view_purchaserequest'],
            pr_permissions['add_purchaserequest'],
            pr_permissions['change_purchaserequest'],
            pr_permissions['approve_purchaserequest_department'],
            pr_permissions['reject_purchaserequest'],
            item_permissions['view_purchaserequestitem'],
            item_permissions['add_purchaserequestitem'],
            item_permissions['change_purchaserequestitem'],
            project_permissions['view_project'],
            dept_permissions['view_department'],
            workflow_permissions['view_approvalworkflow'],
            approval_permissions['view_approval'],
            # attachment_permissions['view_attachment'],
            # attachment_permissions['add_attachment'],
        )
        self.stdout.write('  ✓ ProjectResponsable permissions set')

        # ----- AdministrativeStaff -----
        admin_staff = created_groups['AdministrativeStaff']
        admin_staff.permissions.add(
            pr_permissions['view_purchaserequest'],
            pr_permissions['add_purchaserequest'],
            pr_permissions['change_purchaserequest'],
            item_permissions['view_purchaserequestitem'],
            item_permissions['add_purchaserequestitem'],
            item_permissions['change_purchaserequestitem'],
            project_permissions['view_project'],
            dept_permissions['view_department'],
            workflow_permissions['view_approvalworkflow'],
            approval_permissions['view_approval'],
            # attachment_permissions['view_attachment'],
            # attachment_permissions['add_attachment'],
        )
        self.stdout.write('  ✓ AdministrativeStaff permissions set')

        # ----- DeputyCoordinator -----
        deputy_coord = created_groups['DeputyCoordinator']
        deputy_coord.permissions.add(
            pr_permissions['view_purchaserequest'],
            pr_permissions['approve_purchaserequest_department'],
            pr_permissions['reject_purchaserequest'],
            dept_permissions['view_department'],
            project_permissions['view_project'],
            workflow_permissions['view_approvalworkflow'],
            approval_permissions['view_approval'],
            # attachment_permissions['view_attachment'],
        )
        self.stdout.write('  ✓ DeputyCoordinator permissions set')

        # ----- PurchasingCentral -----
        purchasing = created_groups['PurchasingCentral']
        purchasing.permissions.add(
            pr_permissions['view_purchaserequest'],
            pr_permissions['approve_purchaserequest_purchasing'],
            pr_permissions['reject_purchaserequest'],
            pr_permissions['edit_purchaserequest_purchasing'],
            item_permissions['view_purchaserequestitem'],
            item_permissions['change_purchaserequestitem'],
            project_permissions['view_project'],
            dept_permissions['view_department'],
            workflow_permissions['view_approvalworkflow'],
            approval_permissions['view_approval'],
            # attachment_permissions['view_attachment'],
            # attachment_permissions['add_attachment'],
        )
        self.stdout.write('  ✓ PurchasingCentral permissions set')

        # ----- Logistics (LOGISTICO) -----
        logistics = created_groups['Logistics']
        logistics.permissions.add(
            pr_permissions['view_purchaserequest'],
            item_permissions['view_purchaserequestitem'],
            project_permissions['view_project'],
            dept_permissions['view_department'],
            workflow_permissions['view_approvalworkflow'],
            approval_permissions['view_approval'],
            # attachment_permissions['view_attachment'],
        )
        self.stdout.write('  ✓ Logistics permissions set')

        # ----- HR (RH) -----
        hr = created_groups['HR']
        hr.permissions.add(
            pr_permissions['view_purchaserequest'],
            pr_permissions['add_purchaserequest'],
            pr_permissions['change_purchaserequest'],
            item_permissions['view_purchaserequestitem'],
            item_permissions['add_purchaserequestitem'],
            item_permissions['change_purchaserequestitem'],
            project_permissions['view_project'],
            dept_permissions['view_department'],
            workflow_permissions['view_approvalworkflow'],
            approval_permissions['view_approval'],
            # attachment_permissions['view_attachment'],
            # attachment_permissions['add_attachment'],
        )
        self.stdout.write('  ✓ HR permissions set')

        self.stdout.write(self.style.SUCCESS('\n✓ All groups and permissions created successfully!'))
        self.stdout.write(self.style.SUCCESS(f'Total groups: {len(groups)}'))