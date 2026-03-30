from datetime import datetime
from django.db import models
from app import settings
from core.activity.models import Activity
from core.erp.models import Department
from core.project.models import Project
from core.user.models import User
from django.core.exceptions import ValidationError



class Task(models.Model):
    timesheet = models.ForeignKey('Timesheet', on_delete=models.CASCADE, related_name='tasks')
    project = models.ForeignKey(Project, on_delete=models.CASCADE, null=True)
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE, null=True)
    hour = models.DecimalField(blank=True, null=True, verbose_name='Hora', decimal_places=2, max_digits=5)
    created_at = models.DateField(verbose_name='Data em que o trabalho foi realizado', blank=True, null=True)
    #task_date = models.DateField(auto_now_add=True, verbose_name='Data de criaÃ§Ã£o', blank=True, null=True)
    updated_at = models.DateField(auto_now=True, verbose_name='Data de atualizaÃ§Ã£o', blank=True, null=True)

    TASK_STATUS = [
        ('pending', 'Pendente'),
        ('approved', 'Aprovado'),
        ('rejected', 'Rejeitado'),
        ('needs_improvement', 'SugestÃ£o de Melhoria'),
    ]
    status = models.CharField(max_length=20, choices=TASK_STATUS, default='pending', verbose_name='Estado')
    review_comment = models.TextField(blank=True, null=True, verbose_name='ComentÃ¡rio da RevisÃ£o')

    class Meta:
        verbose_name = 'Tarefa'
        verbose_name_plural = 'Tarefas'
        default_permissions = ()
        permissions = (
            ('view_task', 'Can view Tarefa'),
        )

    def save(self, *args, **kwargs):
        """Salva a tarefa com validaÃ§Ãµes"""
        # Impede modificaÃ§Ãµes em timesheets submetidos
        if self.pk and self.timesheet_id and self.timesheet.status == 'submetido':
            raise ValidationError("NÃ£o Ã© possÃ­vel modificar tarefas de um timesheet jÃ¡ submetido.")

        # âš ï¸ CORREÃ‡ÃƒO: SÃ³ define created_at se nÃ£o for fornecido
        if not self.pk and not self.created_at:
            self.created_at = datetime.now().date()

        # âš ï¸ ADICIONE VALIDAÃ‡ÃƒO DE DATA FUTURA
        if self.created_at and self.created_at > datetime.now().date():
            raise ValidationError({
                'created_at': 'A data da tarefa nÃ£o pode ser futura.'
            })
        super().save(*args, **kwargs)

        # Atualiza o total de horas do timesheet
        if self.timesheet_id:
            self.timesheet.save()

    def delete(self, *args, **kwargs):
        # âš ï¸ CORREÃ‡ÃƒO: MantÃ©m a restriÃ§Ã£o de exclusÃ£o para timesheets submetidos
        if self.timesheet.status == 'submetido':
            raise ValidationError("NÃ£o Ã© possÃ­vel excluir tarefas de um timesheet jÃ¡ submetido.")
        timesheet = self.timesheet
        super().delete(*args, **kwargs)

        # Atualiza o total de horas do timesheet apÃ³s exclusÃ£o
        timesheet.save()

    def clean(self):
        """ValidaÃ§Ãµes da tarefa"""
        # Valida se as horas sÃ£o positivas se preenchidas
        if self.hour is not None and float(self.hour) <= 0:
            raise ValidationError({
                'hour': 'A hora total deve ser maior que zero.'
            })

        # Valida se nÃ£o excede um limite razoÃ¡vel
        if self.hour is not None and float(self.hour) > 16:
            raise ValidationError({
                'hour': 'A hora total nÃ£o pode exceder 16 horas.'
            })

        # Valida se a tarefa nÃ£o Ã© duplicada no mesmo timesheet
        if self.pk is None:  # Apenas para novas tarefas
            duplicate = Task.objects.filter(
                timesheet=self.timesheet,
                project=self.project,
                activity=self.activity
            ).exists()

            if duplicate:
                raise ValidationError(
                    'JÃ¡ existe uma tarefa com este projeto e atividade no timesheet.'
                )

    @property
    def project_name(self):
        return self.project.name if self.project else "N/A"

    @property
    def activity_name(self):
        return self.activity.name if self.activity else "N/A"

    def __str__(self):
        project_name = getattr(self.project, 'name', str(self.project))
        activity_name = getattr(self.activity, 'name', str(self.activity))
        return f"Tarefa #{self.id} - {project_name} - {activity_name} - {self.hour or 0}h"

class Timesheet(models.Model):
    STATUS = [
        ('rascunho', 'Rascunho'),
        ('submetido', 'Submetido'),
        ('em_revisao', 'Em RevisÃ£o'),
        ('aprovado', 'Aprovado'),
        ('com_sugestoes', 'Com SugestÃµes'),
        ('com_rejeitadas', 'Com Rejeitadas'),
    ]
    employee = models.ForeignKey(User, on_delete=models.PROTECT,related_name='timesheets', verbose_name='Colaborador')
    department = models.ForeignKey(Department, on_delete=models.PROTECT, verbose_name='Departamento')
    status = models.CharField(max_length=30, choices=STATUS, verbose_name='Estado', blank=True)
    # description = models.CharField(max_length=255, verbose_name='DescriÃ§Ã£o', null=True, blank=True)
    obs = models.TextField(verbose_name='ObservaÃ§Ã£o', null=True, blank=True)
    total_hour = models.DecimalField(blank=True, null=True, verbose_name='Total de horas', decimal_places=2,
                                     max_digits=5)

    created_at = models.DateField(auto_now_add=True, verbose_name='Data de criaÃ§Ã£o', null=True, blank=True)
    updated_at = models.DateField(auto_now=True, verbose_name='Data de atualizaÃ§Ã£o')
    submitted_at = models.DateField(verbose_name='Data de submissÃ£o', null=True)
    submitted_by = models.ForeignKey(User, on_delete=models.PROTECT, verbose_name='Submetido por', null=True, blank=True, related_name='submitted_timesheets')
    locked_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='locked_timesheets', verbose_name='Trancado por')
    locked_at = models.DateTimeField(null=True, blank=True, verbose_name='Trancado em')

    def __str__(self):
        employee_name = self.employee.get_full_name() if self.employee else 'Sem colaborador'
        return f"Timesheet #{self.id} - {employee_name} - {self.get_status_display()}"
    @property
    def employee_name(self):
        return self.employee.get_full_name()  # ou .full_name, conforme seu modelo

    def submitted_name(self):
        return self.submitted_by.get_full_name()  # ou .full_name, conforme seu modelo

    @property
    def department_name(self):
        return self.department.name

    @property
    def locked_by_name(self):
        return self.locked_by.get_full_name() if self.locked_by else None

    def calculate_total_hours(self):
        return self.tasks.aggregate(total=models.Sum('hour'))['total'] or 0

    def save(self, *args, **kwargs):
        """Atualiza automaticamente o total de horas baseado nas tarefas"""
        is_new = self._state.adding

        # Salva primeiro para ter um ID se for novo
        if is_new:
            super().save(*args, **kwargs)

        # Atualiza o total de horas baseado nas tarefas
        if self.pk:
            self.total_hour = self.calculate_total_hours()

        # Para novos registros, jÃ¡ salvamos acima
        if not is_new:
            super().save(*args, **kwargs)

    def get_status_display(self):
        return dict(self.STATUS).get(self.status,'Desconhecido')

    def clean(self):
        """ValidaÃ§Ãµes do modelo"""
        if self.status == 'submetido' and self.pk:
            # Verifica se tem tarefas antes de submeter
            if self.tasks.count() == 0:
                raise ValidationError("NÃ£o Ã© possÃ­vel submeter um timesheet sem tarefas.")

            # Verifica se todas as tarefas tÃªm horas preenchidas
            invalid_tasks = self.tasks.filter(hour__isnull=True)
            if invalid_tasks.exists():
                raise ValidationError("Todas as tarefas devem ter horas preenchidas antes de submeter.")

            # Opcional: validar horas vÃ¡lidas
            if self.tasks.filter(hour__lte=0).exists():
                raise ValidationError("As horas das tarefas devem ser maiores que zero.")



    def can_add_task(self):
        """ Verifica se pode adicionar mais tarefas (limite opcional) """
        return self.status in ('rascunho', 'com_sugestoes', 'com_rejeitadas')

    def can_remove_task(self):
        """ Verifica se pode remover tarefas """
        return self.status == 'rascunho'

    def can_edit(self):
        """ Verifica se o timesheet pode ser editado """
        return self.status in ('rascunho', 'com_sugestoes', 'com_rejeitadas')

    def submit(self):
        """ MÃ©todo para submeter o timesheet """
        if not self.can_edit():
            raise ValidationError("Timesheet jÃ¡ foi submetido e nÃ£o pode ser alterado.")

        # Executa as validaÃ§Ãµes do clean()
        self.full_clean()
        self.submitted_at = datetime.now().date()

        self.status = 'submetido'
        self.save()



    def reopen(self):
        """MÃ©todo para reabrir um timesheet submetido (se necessÃ¡rio)"""
        if self.status == 'submetido':
            self.status = 'rascunho'
            self.save()

    class Meta:
        verbose_name = 'Timesheet'
        verbose_name_plural = 'Timesheets'
        default_permissions = ()
        permissions = (
            ('view_timesheet', 'Can view Timesheet'),
        )

class TimesheetComment(models.Model):
    timesheet = models.ForeignKey('Timesheet', on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name='Colaborador')
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

class TimesheetStatusChange(models.Model):
    timesheet = models.ForeignKey('Timesheet', on_delete=models.CASCADE, related_name='status_changes')
    old_status = models.CharField(max_length=20)
    new_status = models.CharField(max_length=20)
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name='Colaborador')
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']


# class EmployeeWorkSettings(models.Model):
#     employee = models.OneToOneField(User, on_delete=models.CASCADE, related_name='work_settings')
#     weekly_hours_target = models.DecimalField(default=40, decimal_places=2, max_digits=5)
#     daily_hours_target = models.DecimalField(default=8, decimal_places=2, max_digits=5)
#     preferred_work_days = models.CharField(max_length=13, default="1,2,3,4,5")  # Seg-Sex
#     created_at = models.DateTimeField(auto_now_add=True)
#     updated_at = models.DateTimeField(auto_now=True)
