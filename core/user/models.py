from datetime import timedelta, date

from crum import get_current_request
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Sum, F, DurationField
from django.forms import model_to_dict
from app.settings import MEDIA_URL, STATIC_URL
from core.erp.models import Department
from core.homepage.models import Absence, Position


class User(AbstractUser):
    image = models.ImageField(upload_to='users/%Y%m%d', blank=True, null=True)
    max_days_year = models.PositiveIntegerField(default=22, blank=True, null=True)
    available_days = models.PositiveIntegerField(default=0, blank=True, null=True)
    used_days = models.PositiveIntegerField(default=0, blank=True, null=True)
    hold_days = models.PositiveIntegerField(default=0, blank=True, null=True)

    department = models.ForeignKey(Department, on_delete=models.CASCADE, blank=True, null=True, verbose_name='Departamento')
    position = models.ForeignKey(Position, on_delete=models.CASCADE, blank=True, null=True, verbose_name='Cargo')


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
        print(self.department)
        item['department'] = self.department.toJson()
        item['position'] = self.position.toJson()

        item['full_name'] = self.get_full_name()
        item['groups'] = [{'id': g.id, 'name': g.name} for g in self.groups.all()]
        print(item)
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


    def atualizar_ferias_anuais(self):
        # Calcula o total de dias de ausência aprovados para o usuário
        total_ausencias_aprovadas = Absence.objects.filter(
            User=self.user, status='Aprovado'
        ).aggregate(total_dias=Sum(F('end_date') - F('start_date'), output_field=DurationField()))[
                                        'total_dias'] or timedelta(days=0)

        # Considera o limite máximo de 22 dias por ano
        # dias_maximos_por_ano = 22

        # Calcula os dias acumulados do ano anterior (se houver)
        dias_acumulados_anterior = self.available_days - self.max_days_year
        if dias_acumulados_anterior < 0:
            dias_acumulados_anterior = 0

        # Atualiza o saldo de férias anuais
        self.available_days = max(0,
                                  dias_acumulados_anterior + self.max_days_year - total_ausencias_aprovadas.days)
        self.save()

    def calcular_dias_disponiveis(self):
        total_available_days = self.available_days
        ano_atual = date.today().year
        ausencias_ano_atual = Absence.objects.filter(data_inicio__year=ano_atual, User=self.user, status='Aprovado')
        for ausencia in ausencias_ano_atual:
            total_available_days -= (ausencia.end_date - ausencia.start_date).days
        self.available_days = max(0, total_available_days)
        self.save()

    def notificacao_ferias_seis_meses(self):
        # Calcula a data há 6 meses atrás
        data_seis_meses_atras = date.today() - timedelta(days=180)

        # Filtra as ausências nos últimos 6 meses
        ausencias_seis_meses = Absence.objects.filter(data_inicio__gte=data_seis_meses_atras)

        # Calcula o total de dias de ausência nos últimos 6 meses
        total_dias_ausencia_seis_meses = sum(
            (ausencia.end_date - ausencia.start_date).days + 1 for ausencia in ausencias_seis_meses)

        # Calcula os dias disponíveis de férias atualmente
        dias_disponiveis = self.calcular_dias_disponiveis()

        # Verifica se o funcionário tem mais de 22 dias de férias disponíveis após 6 meses
        if total_dias_ausencia_seis_meses == 0 and dias_disponiveis > 22:
            # Envia a notificação para o funcionário
            Notification.objects.create(
                funcionario=self,
                mensagem=f"Você tem mais de 22 dias de férias disponíveis após 6 meses. Por favor, planeje suas férias."
            )

    def __str__(self):
        return self.get_full_name()

class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    mensagem = models.TextField()
    lida = models.BooleanField(default=False)
    criado_em = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.mensagem
