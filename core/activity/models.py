from django.db import models

from core.erp.models import Department


class Activity(models.Model):
    name = models.CharField(max_length=255)
    description = models.CharField(max_length=255, blank=True, null=True)
    department = models.ForeignKey(Department, on_delete=models.CASCADE)
    is_active = models.BooleanField(default=True, blank=False)
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, null=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = 'Actividade'
        verbose_name_plural = 'Actividades'
        default_permissions = ()
        permissions = (
            ('view_activity', 'Can view Actividade'),
        )


