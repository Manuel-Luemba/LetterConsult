from ckeditor.fields import RichTextField
from crum import get_current_user
from django.db import models
from django.forms import model_to_dict
from django.utils import timezone


from app.settings import AUTH_USER_MODEL
from core.models import BaseModel
from app.util import *



class Department(models.Model):

    """
    Representa um departamento da empresa.
    - Pode ter múltiplos coordenadores e coordenadores adjuntos.
    - É o centro de custo para requisições departamentais.
    - Utilizado no timesheet e no sistema de requisições.
    """

    name = models.CharField(max_length=250, verbose_name='Nome', unique=True)
    abbreviation = models.CharField(max_length=70, verbose_name='Abreviatura', unique=True, null=True, blank=True)
    manager = models.OneToOneField(AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='managed_department',
                                   verbose_name='Coordenador')

    # 👉 NOVO: Múltiplos coordenadores
    managers = models.ManyToManyField(
        AUTH_USER_MODEL,
        related_name='managed_departments',
        verbose_name='Coordenadores',
        blank=True,
        help_text='Múltiplos coordenadores permitidos'
    )

    # 👉 NOVO: Coordenadores Adjuntos
    deputy_managers = models.ManyToManyField(
        AUTH_USER_MODEL,
        related_name='deputy_managed_departments',
        verbose_name='Coordenadores Adjuntos',
        blank=True,
        help_text='Coordenadores adjuntos - mesma autoridade'
    )

    #counter = models.IntegerField(default=0, null=True, blank=True)
    desc = models.TextField(max_length=400, blank=True, verbose_name='Descrição', null=True)
    is_active = models.BooleanField(default=True, null=True, blank=True)
    cost_center = models.CharField(verbose_name='Centro de custo', max_length=255, null=True, blank=True)

    # Auditoria
    created_at = models.DateTimeField(auto_now_add=True, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, blank=True, null=True)


    def toJson(self):
        item = model_to_dict(self)
        if self.manager is not None:
            item['manager'] = self.manager.get_full_name()
        return item

    def __str__(self):
        return self.name

    @property
    def manager_name(self):
        return self.manager.get_full_name() if self.manager else None

    def manager_names(self):
        return [m.get_full_name() for m in self.managers.all()]

    def deputy_manager_names(self):
        return [dm.get_full_name() for dm in self.deputy_managers.all()]

    @property
    def all_approvers(self):
        """Retorna todos os utilizadores com autoridade de aprovação"""
        managers_list = list(self.managers.all())
        deputy_list = list(self.deputy_managers.all())

        # Inclui o manager legado se existir e não estiver duplicado
        if self.manager and self.manager not in managers_list:
            managers_list.append(self.manager)

        return managers_list + deputy_list

    def can_be_approved_by(self, user):
        """Verifica se o utilizador pode aprovar requisições"""
        return user in self.all_approvers

    @property
    def get_cost_center(self):
        """
        Centro de custo do departamento.
        Nota: Atualmente não existe campo cost_center em Department.
        Sugestão: Adicionar futuramente se necessário.
        """
        return self.cost_center

    class Meta:
        verbose_name = 'departamento'
        verbose_name_plural = 'departamentos'
        db_table = 'departamento'
        ordering = ['id']

class Reference(BaseModel):
    reference_code = models.CharField(max_length=250, unique=True, blank=True, verbose_name="Código de Referência")
    user_department = models.CharField(max_length=250, blank=True, null=True, verbose_name="Departamento")

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

    comment_rejected = models.TextField(blank=True, null=True, verbose_name='Comentário de rejeição')
    comment_review = models.TextField(blank=True, null=True, verbose_name='Comentário de revisão')
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


class Notification(models.Model):
    """
    Sistema de notificações event-driven.
    Cada evento do workflow cria notificações para os utilizadores relevantes.
    """
    EVENT_CHOICES = [
        ('RQ_SUBMITTED', 'Requisição Submetida'),
        ('RQ_APPROVED_DEPT', 'Aprovada (Dept/Projeto)'),
        ('RQ_REJECTED_DEPT', 'Rejeitada (Dept/Projeto)'),
        ('RQ_SENT_PURCHASING', 'Enviada para Central'),
        ('RQ_APPROVED_PURCHASING', 'Aprovada (Central)'),
        ('RQ_REJECTED_PURCHASING', 'Rejeitada (Central)'),
        ('RQ_FORWARDED_DIRECTOR', 'Encaminhada para Direção'),
        ('RQ_APPROVED_DIRECTOR', 'Aprovada (Direção)'),
        ('RQ_REJECTED_DIRECTOR', 'Rejeitada (Direção)'),
        ('RQ_PURCHASING_EDITED', 'Editada pela Central'),
        ('RQ_APPROVED_FINAL', 'Aprovação Final'),
        ('OTHER', 'Outro'),
    ]

    user = models.ForeignKey(AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    message = models.TextField()
    event_type = models.CharField(max_length=50, choices=EVENT_CHOICES, default='OTHER')
    notification_key = models.CharField(max_length=200, unique=True, null=True, blank=True,
                                         help_text='Chave única para deduplicação (ex: RQ-123|RQ_SUBMITTED|user_45)')
    purchase_request_id = models.IntegerField(null=True, blank=True,
                                               help_text='ID da requisição associada')
    action_url = models.CharField(max_length=500, blank=True, default='',
                                   help_text='Link direto para ação (ex: /requisicoes/123)')
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'notification'
        verbose_name = 'notification'
        verbose_name_plural = 'notifications'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['notification_key']),
        ]

    def __str__(self):
        return f"[{self.event_type}] {self.user} — {self.message[:50]}"

