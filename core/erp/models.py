from datetime import datetime

from ckeditor.fields import RichTextField
from crum import get_current_user
from django.db import models
from django.forms import model_to_dict
from django_ckeditor_5.fields import CKEditor5Field

from app.settings import AUTH_USER_MODEL
from core.models import BaseModel
from app.util import *


class Department(models.Model):
    name = models.CharField(max_length=250, verbose_name='Nome', unique=True)
    abbreviation = models.CharField(max_length=70, verbose_name='Abreviatura', unique=True, null=True, blank=True)
    manager = models.OneToOneField(AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='managed_department',
                                   verbose_name='Chefe de departamento')
    counter = models.IntegerField(default=0)
    desc = models.TextField(max_length=400, blank=True, verbose_name='Descrição')

    def toJson(self):
        item = model_to_dict(self)
        if self.manager != None:
            item['manager'] = self.manager.get_full_name()
        return item

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = 'departamento'
        verbose_name_plural = 'departamentos'
        db_table = 'departamento'
        ordering = ['id']


class Reference(BaseModel):
    reference_code = models.CharField(max_length=250, unique=True, blank=True)
    user_department = models.CharField(max_length=250, blank=True, null=True)

    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
        user = get_current_user()
        if user is not None:
            if not self.pk:
                self.user_created = user
            else:
                self.user_updated = user

        super(Reference, self).save()

    def toJson(self):
        item = model_to_dict(self)
        item['date_created'] = self.date_created.strftime('%Y-%m-%d')
        item['user_created'] = self.user_created.get_full_name()
        return item

    def __str__(self):
        return self.reference_code

    class Meta:
        verbose_name = 'referencia'
        verbose_name_plural = 'referencias'
        db_table = 'referencia'
        ordering = ['id']


class Letter(BaseModel):
    letter_status = [
        ('', 'Selecione uma opção'),  # Primeira opção vazia
        ('drafted', 'Rascunho'),
        ('submitted', 'Submetida para Aprovação'),
        ('approved', 'Aprovada'),
        ('rejected', 'Rejeitada'),
        ('sent', 'Enviada'),
    ]
    reference_code = models.ForeignKey(Reference, max_length=250, on_delete=models.CASCADE, null=False, blank=False,
                                       verbose_name='Código de referência')
    recipient = models.CharField(max_length=200, blank=True, null=True,
                                 verbose_name='Destinatário')
    job = models.CharField(max_length=200, blank=True, null=True,
                           verbose_name='Função')
    city = models.CharField(max_length=200, blank=True, null=True,
                            verbose_name='Cidade')

    entity = models.CharField(max_length=200, blank=True, null=True,
                              verbose_name='Entidade')

    title = models.CharField(max_length=255, blank=True, null=True,
                             verbose_name='Assunto')
    content = RichTextField(blank=True, null=True)

    department = models.ForeignKey('Department', on_delete=models.CASCADE)

    date_sent = models.DateTimeField(
        verbose_name='Data de expedição')
    status = models.CharField(max_length=20, choices=letter_status, default=letter_status[0][0], blank=False,
                              null=False,
                              verbose_name='Estado')

    coment_rejected = models.TextField(blank=True, null=True, verbose_name='Comentário de rejeição')
    coment_review = models.TextField(blank=True, null=True, verbose_name='Comentário de revisão')
    protocol = models.FileField(blank=True, null=True, upload_to='uploads/%Y/%m/%d/', verbose_name='Protocolo')

    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
        previous_status = None
        if self.pk:  # Se a carta já existe, pegamos o status anterior
            previous_status = Letter.objects.get(pk=self.pk).status
        user = get_current_user()
        if user is not None:
            if not self.pk:
                self.user_created = user
            else:
                self.user_updated = user

        super(Letter, self).save()

        # Verifica se a carta foi submetida
        if previous_status != 'submitted' and self.status == 'submitted':
            send_submission_email(self)

        # Verifica se a carta foi aprovada ou rejeitada
        if previous_status != self.status and self.status in ['approved', 'rejected']:
            send_approval_rejection_email(self)

            # Verifica se a carta foi enviada
            if previous_status != 'sent' and self.status == 'sent':
                send_letter_sent_email_with_attachment(self)  # Chama a função do util.py para enviar o e-mail com anexo

    def get_status_display(self):
        # Procura no `letter_status` a tupla onde a chave bate com o valor atual de status
        for key, display_value in self.letter_status:
            if self.status == key:
                return display_value
        return None  # Retorna None se não encontrar o valor

    def toJson(self):
        item = model_to_dict(self, exclude='protocol')
        item['date_sent'] = self.date_sent.strftime('%Y-%m-%d')
        item['reference_code'] = self.reference_code.reference_code
        item['date_created'] = self.date_created.strftime('%Y-%m-%d')
        item['date_updated'] = self.date_created.strftime('%Y-%m-%d')
        item['user_created'] = self.user_created.get_full_name()
        item['status_desc'] = self.get_status_display()
        item['department_name'] = self.department.name
        return item

    def __str__(self):
        return str(self.id)

    class Meta:
        verbose_name = 'carta'
        verbose_name_plural = 'cartas'
        db_table = 'carta'
        ordering = ['id']
