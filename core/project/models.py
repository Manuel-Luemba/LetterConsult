from django.db import models

from app.settings import AUTH_USER_MODEL
from core.erp.models import Department



class Project(models.Model):
    name = models.CharField(verbose_name='Nome', max_length=255, blank=True, null=True)
    description = models.CharField(verbose_name='Descrição', max_length=255, null=True, blank=True)
    cod_contractor = models.CharField(verbose_name='Codigo do Empreteiro', max_length=255, null=True, blank=True)
    cod_supervision = models.CharField(verbose_name='Codigo da Supervisão', max_length=255, null=True, blank=True)
    cost_center = models.CharField(verbose_name='Centro de custo', max_length=255, null=True, blank=True)
    localization = models.CharField(verbose_name='Localização', max_length=255, null=True, blank=True)
    is_active = models.BooleanField(verbose_name='Estado', default=True, null=True, blank=True)

    #👉 ATIVAR: Department FK (estava comentado)
    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='projects',
        verbose_name='Departamento Responsável'
    )
    #
    # # 👉 NOVO: Responsáveis do projeto (MÚLTIPLOS)
    responsible = models.ManyToManyField(
        AUTH_USER_MODEL,
        related_name='responsible_projects',
        verbose_name='Responsáveis do Projeto',
        blank=True,
        help_text='Podem aprovar requisições do projeto'
    )
    #
    # # 👉 NOVO: Team Leader (OPCIONAL)
    team_leader = models.ForeignKey(
        AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='led_projects',
        verbose_name='Team Leader'
    )

    # 👉 NOVO: Administrativos alocados
    administrative_staff = models.ManyToManyField(
        AUTH_USER_MODEL,
        related_name='administrative_projects',
        verbose_name='Administrativos',
        blank=True,
        help_text='Funcionários administrativos alocados ao projeto'
    )

    # # 👉 NOVO: Datas para ciclo de vida
    start_date = models.DateField(verbose_name='Data de Início', null=True, blank=True)
    end_date = models.DateField(verbose_name='Data de Término', null=True, blank=True)

    class Meta:
        verbose_name = 'Projeto'
        verbose_name_plural = 'Projetos'
        default_permissions = ()
        permissions = (
            ('view_project', 'Can view Projeto'),
        )

    def __str__(self):
        return self.name or "Sem nome"

    @property
    def has_team_leader(self):
        """Verifica se projeto tem team leader definido"""
        return self.team_leader is not None

    @property
    def all_approvers(self):
        """Todos os aprovadores do projeto"""
        approvers = list(self.responsible.all())
        if self.team_leader:
            approvers.append(self.team_leader)
        return approvers

    def get_all_approvers(self):
        """Interface para sistema de requisições"""
        return self.all_approvers

    def can_be_approved_by(self, user):
        """Verifica se user pode aprovar requisições deste projeto"""
        if self.team_leader and user == self.team_leader:
            return True
        return user in self.responsible.all()

    def user_belongs_to_project(self, user):
        """Verifica se user está alocado no projeto"""
        return any([
            user == self.team_leader,
            user in self.responsible.all(),
            user in self.administrative_staff.all()
        ])



