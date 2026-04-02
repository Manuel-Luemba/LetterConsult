from django.test import TestCase
from django.contrib.auth.models import Group
from core.user.models import User
from core.erp.models import Department, Notification
from core.timesheet.models import Timesheet, Task
from core.timesheet.services.timesheet_workflow_service import TimesheetWorkflowService
from core.activity.models import Activity
from datetime import date, timedelta
from decimal import Decimal

class TimesheetWorkflowTest(TestCase):
    def setUp(self):
        # 1. Criar departamentos e grupos
        self.dept = Department.objects.create(name="TI", abbreviation="TI")
        # Usamos o nome 'Manager' que é reconhecido pelo is_approver do modelo User
        self.group_mgr = Group.objects.create(name="Manager")
        
        # 2. Criar usuários (Colaborador e Gestor)
        self.user_emp = User.objects.create_user(username="emp", email="emp@test.com", password="pwd")
        self.user_mgr = User.objects.create_user(username="mgr", email="mgr@test.com", password="pwd")
        
        # Simular is_approver
        self.user_mgr.groups.add(self.group_mgr)
        self.user_mgr.department = self.dept
        self.user_mgr.save()

        # 3. Criar Atividade para as tarefas
        self.activity = Activity.objects.create(name="Desenvolvimento", department=self.dept)

        # 4. Criar Timesheet (Rascunho)
        self.ts = Timesheet.objects.create(
            employee=self.user_emp,
            department=self.dept,
            status='rascunho'
        )
        
        # Adicionar uma tarefa (obrigatório para submissão)
        Task.objects.create(
            timesheet=self.ts,
            activity=self.activity,
            hour=Decimal("8.0"),
            created_at=date.today() - timedelta(days=1)
        )

    def test_workflow_submission_and_notification(self):
        """Testa se a submissão altera o status e cria notificações."""
        # Garantir que o gestor é um approver antes de começar
        self.assertTrue(self.user_mgr.is_approver)
        
        service = TimesheetWorkflowService(self.ts)
        service.submit_for_approval(self.user_emp)
        
        self.ts.refresh_from_db()
        self.assertEqual(self.ts.status, 'submetido')
        
        # Verificar se a notificação foi criada para o gestor
        notif = Notification.objects.filter(user=self.user_mgr, timesheet_id=self.ts.id).first()
        self.assertIsNotNone(notif)
        self.assertEqual(notif.event_type, 'TS_SUBMITTED')

    def test_workflow_approval_and_notification(self):
        """Testa se a aprovação altera o status e notifica o colaborador."""
        self.ts.status = 'submetido'
        self.ts.save()
        
        service = TimesheetWorkflowService(self.ts)
        service.approve(self.user_mgr, "Aprovado com sucesso")
        
        self.ts.refresh_from_db()
        self.assertEqual(self.ts.status, 'aprovado')
        
        # Verificar se o colaborador foi notificado
        notif = Notification.objects.filter(user=self.user_emp, timesheet_id=self.ts.id).first()
        self.assertIsNotNone(notif)
        self.assertEqual(notif.event_type, 'TS_ACTION_TAKEN')

    def test_workflow_rejection_and_notification(self):
        """Testa se a rejeição altera o status e notifica o colaborador."""
        self.ts.status = 'submetido'
        self.ts.save()
        
        service = TimesheetWorkflowService(self.ts)
        service.reject(self.user_mgr, "Horas incorretas")
        
        self.ts.refresh_from_db()
        self.assertEqual(self.ts.status, 'com_rejeitadas')
        
        # Verificar se o colaborador foi notificado
        notif = Notification.objects.filter(user=self.user_emp, timesheet_id=self.ts.id).first()
        self.assertIsNotNone(notif)
        self.assertIn("Horas incorretas", notif.message)
