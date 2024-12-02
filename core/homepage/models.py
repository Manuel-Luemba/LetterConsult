from django.db import models

from core.models import BaseModel
from crum import get_current_user
from django.forms import model_to_dict
from workalendar.africa import Angola  # Substitua pelo calendário do seu país

from core.user.choices import absence_status


class Type(models.Model):
    name = models.CharField(max_length=250, verbose_name='Nome')
    desc = models.TextField(max_length=400, blank=True, null=True, verbose_name='Descrição')

    def toJson(self):
        item = model_to_dict(self)
        return item

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = 'tipo'
        verbose_name_plural = 'tipos'
        db_table = 'tipo'
        ordering = ['id']


class Absence(BaseModel):
    type = models.ForeignKey(Type, models.CASCADE, verbose_name='Tipo da ausência', blank=True, null=True)
    start_date = models.DateField(verbose_name='Data de inicio', blank=True, null=True)
    end_date = models.DateField(verbose_name='Data de fim', blank=True, null=True)
    reason = models.TextField(max_length=400, verbose_name='Motivo da ausência', blank=True, null=True)
    status = models.CharField(max_length=20, choices=absence_status, default=absence_status[0][0], blank=True, null=True,
                              verbose_name='Estado')
    days_absence = models.PositiveIntegerField(verbose_name='Periodo', blank=True, null=True)
    obs = models.TextField(max_length=400, verbose_name='Obs', blank=True, null=True)
    # file = models.FileField(upload_to='uploads/%Y%m%d', blank=True, null=True, verbose_name='Justificativo')



    def calcular_dias_uteis(self, start, end):
        cal = Angola()  # Defina o calendário brasileiro (ou o correspondente ao seu país)
        dias_uteis = cal.get_working_days_delta(start, end) + 1
        return dias_uteis

    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
        self.days_absence = self.calcular_dias_uteis(self.start_date, self.end_date)
        user = get_current_user()
        if user is not None:
            if not self.pk:
                self.user_created = user
            else:
                self.user_updated = user
        print(user.max_days_year, 'dias de ferias no ano')
        #print(user.available_days, '')

        if self.end_date > self.start_date:
            print("MSNND " ,self.calcular_dias_uteis(self.end_date,self.start_date))
            self.days_absence = self.calcular_dias_uteis(self.end_date,self.start_date)
        if not user.max_days_year < self.days_absence:
            print("saved")
            super(Absence, self).save()

    def __str__(self):
        return self.status

    def toJson(self):
        item = model_to_dict(self, exclude="file")
        item['type'] = self.type.name
        #item['type'] = self.type_ab.name
        item['start_date'] = self.start_date.strftime('%Y-%m-%d')
        item['end_date'] = self.end_date.strftime('%Y-%m-%d')
        item['user_created'] = self.user_created.get_full_name()
        return item

    class Meta:
        verbose_name = 'ausencia'
        verbose_name_plural = 'ausencias'
        db_table = 'ausencia'
        ordering = ['id']
        permissions = (("aprove_absence", "Can aprove ausencia"), ("aprove_up_absence", "Can up aprove ausencia"),)


class Position(models.Model):
    name = models.CharField(max_length=250, verbose_name='Nome')
    desc = models.TextField(max_length=400, blank=True, null=True, verbose_name='Descrição')

    def toJson(self):
        item = model_to_dict(self)
        return item

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = 'cargo'
        verbose_name_plural = 'cargos'
        db_table = 'cargo'
        ordering = ['id']
