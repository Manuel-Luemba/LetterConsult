# Generated by Django 4.2.10 on 2024-06-05 10:57

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('erp', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='department',
            name='manager',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='managed_department', to=settings.AUTH_USER_MODEL, verbose_name='Chefe de departamento'),
        ),
    ]