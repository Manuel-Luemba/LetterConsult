# Generated by Django 4.2.10 on 2024-02-20 11:08

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('erp', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='department',
            name='description',
        ),
        migrations.RemoveField(
            model_name='position',
            name='description',
        ),
        migrations.RemoveField(
            model_name='type',
            name='description',
        ),
        migrations.AddField(
            model_name='department',
            name='desc',
            field=models.TextField(blank=True, max_length=400, verbose_name='Descrição'),
        ),
        migrations.AddField(
            model_name='position',
            name='desc',
            field=models.TextField(blank=True, max_length=400, null=True, verbose_name='Descrição'),
        ),
        migrations.AddField(
            model_name='type',
            name='desc',
            field=models.TextField(blank=True, max_length=400, null=True, verbose_name='Descrição'),
        ),
        migrations.AlterField(
            model_name='department',
            name='name',
            field=models.CharField(max_length=250, unique=True, verbose_name='Nome'),
        ),
        migrations.AlterField(
            model_name='position',
            name='name',
            field=models.CharField(max_length=250, verbose_name='Nome'),
        ),
        migrations.AlterField(
            model_name='type',
            name='name',
            field=models.CharField(max_length=250, verbose_name='Nome'),
        ),
    ]