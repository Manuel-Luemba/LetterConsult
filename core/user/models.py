from crum import get_current_request
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Q
from django.forms import model_to_dict
from app.settings import MEDIA_URL, STATIC_URL
from core.erp.models import Department
from core.homepage.models import Absence, Position
from core.project.models import Project


class User(AbstractUser):
    image = models.ImageField(upload_to='users/%Y%m%d', blank=True, null=True)
    department = models.ForeignKey(Department, on_delete=models.CASCADE, blank=True, null=True,
                                   verbose_name='Departamento')
    position = models.ForeignKey(Position, on_delete=models.CASCADE, blank=True, null=True, verbose_name='Cargo')

    # limite_aprovacao = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    # pode_aprovar = models.BooleanField(default=False)
    # digital_sign = models.TextField(null=True, blank=True)  # Para futura integração

    def __str__(self):
        return self.get_full_name()

    def get_full_name(self):
        return '{} {}'.format(self.first_name, self.last_name)

    # ----- PROPERTIES DE GRUPOS ROBUSTAS -----
    @property
    def group_names(self):
        return [group.name for group in self.groups.all()]

    def _has_group_like(self, *patterns):
        """Verifica se o usuário pertence a algum grupo que contenha um dos padrões (case-insensitive)"""
        groups = self.group_names
        for group in groups:
            name = group.lower()
            if any(p.lower() in name for p in patterns):
                return True
        return False

    @property
    def is_administrator(self):
        return self.is_superuser or self.is_staff or self._has_group_like('admin', 'administrator', 'administrador')

    @property
    def is_manager(self):
        return (
            self._has_group_like('manager', 'gerente') or 
            hasattr(self, 'managed_department') or 
            self.managed_departments.exists()
        )

    @property
    def is_director(self):
        return self._has_group_like('director', 'diretor')

    @property
    def is_deputy_director(self):
        return self._has_group_like('deputy', 'adjunto', 'vice')

    @property
    def is_purchasing_central(self):
        return self._has_group_like('purchasing', 'compras', 'central')

    @property
    def is_team_leader(self):
        return (
            self._has_group_like('teamleader', 'lider', 'chefe') or 
            self.led_projects.exists()
        )

    @property
    def is_project_responsible(self):
        return (
            self._has_group_like('projectresponsable', 'responsavel') or 
            self.responsible_projects.exists()
        )

    @property
    def is_deputy_coordinator(self):
        return (
            self._has_group_like('deputycoordinator', 'coordenador', 'adjundo') or 
            self.deputy_managed_departments.exists()
        )

    @property
    def is_approver(self):
        """Define se o utilizador pode aprovar alguma fase do workflow."""
        return (
            self.is_manager or 
            self.is_director or 
            self.is_administrator or 
            self.is_purchasing_central or 
            self.is_team_leader or 
            self.is_project_responsible or 
            self.is_deputy_coordinator or
            self._has_group_like('logistica', 'logistics')
        )

    # ----- MÉTODOS EXISTENTES (MANTIDOS) -----

    def get_image(self):
        if self.image:
            return '{}{}'.format(MEDIA_URL, self.image)
        return '{}{}'.format(STATIC_URL, 'img/empty.png')

    def toJSON(self):
        item = model_to_dict(self, exclude=['password', 'user_permissions', 'last_login'])
        if self.last_login:
            item['last_login'] = self.last_login.strftime('%Y-%m-%d')

        item['date_joined'] = self.date_joined.strftime('%Y-%m-%d')
        item['image'] = self.get_image()

        item['department'] = self.department.toJson() if self.department else None
        item['position'] = self.position.toJson() if self.position else None

        item['full_name'] = self.get_full_name()
        item['groups'] = [{'id': g.id, 'name': g.name} for g in self.groups.all()]

        return item

    def get_group_session(self):
        try:
            request = get_current_request()
            groups = self.groups.all()
            if groups.exists():
                if 'group' not in request.session:
                    request.session['group'] = groups[0]
        except:
            pass

    def save(self, *args, **kwargs):
        super().save()
    # ----- REGRAS DE NEGÓCIO -----
    @property
    def is_in_project(self):
        """Verifica se o utilizador está alocado em algum projeto ativo."""
        return Project.objects.filter(
            Q(team_leader=self) |
            Q(responsables=self) |
            Q(administrative_staff=self),
            is_active=True
        ).exists()

    def get_current_project(self):
        """Retorna o projeto atual (prioridade: Team Leader > Responsável > Administrativo)."""
        # Team Leader
        project = Project.objects.filter(team_leader=self, is_active=True).first()
        if project:
            return project
        # Responsável
        project = Project.objects.filter(responsables=self, is_active=True).first()
        if project:
            return project
        # Administrativo
        project = Project.objects.filter(administrative_staff=self, is_active=True).first()
        return project

    def approves_directly_to_purchasing(self):
        """
        Quem NÃO precisa aprovação departamental?
        - Team Leader, Project Responsable, Manager, DeputyCoordinator, Director, DeputyDirector
        """
        direct_groups = [
            'TeamLeader', 'ProjectResponsable', 'Manager',
            'DeputyCoordinator', 'Director', 'DeputyDirector'
        ]
        return any(group in self.group_names for group in direct_groups)

# class EmployeeWorkSettings(models.Model):
#     employee = models.OneToOneField(User, on_delete=models.CASCADE, related_name='work_settings')
#     weekly_hours_target = models.DecimalField(default=40, decimal_places=2, max_digits=5)
#     daily_hours_target = models.DecimalField(default=8, decimal_places=2, max_digits=5)
#     preferred_work_days = models.CharField(max_length=13, default="1,2,3,4,5")  # Seg-Sex
#     created_at = models.DateTimeField(auto_now_add=True)
#     updated_at = models.DateTimeField(auto_now=True)
#
# class EmployeeHRProfile(models.Model):
#     employee = models.OneToOneField(User, on_delete=models.CASCADE, related_name='hr_profile')
#     bi = models.CharField(max_length=20)
#     salary = models.DecimalField(max_digits=10, decimal_places=2)
#     profit = models.TextField(blank=True, null=True)
#
# class PurchaseProfile(models.Model):
#     employee = models.OneToOneField(User, on_delete=models.CASCADE, related_name='purchase_profile')
#     limite_aprovacao = models.DecimalField(max_digits=10, decimal_places=2)
#     centro_compras = models.CharField(max_length=100)
