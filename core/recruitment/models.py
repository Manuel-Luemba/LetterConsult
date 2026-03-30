from django.db import models
from core.models import BaseModel
from django.forms import model_to_dict

class JobVacancy(BaseModel):
    title = models.CharField(max_length=255, verbose_name="Título da Vaga")
    description = models.TextField(verbose_name="Descrição")
    requirements = models.TextField(verbose_name="Requisitos")
    responsibilities = models.TextField(verbose_name="Responsabilidades")
    location = models.CharField(max_length=255, verbose_name="Localização")
    salary_range = models.CharField(max_length=255, blank=True, null=True, verbose_name="Média Salarial")
    education_level = models.CharField(max_length=255, verbose_name="Escolaridade Exigida")
    is_active = models.BooleanField(default=True, verbose_name="Ativa")
    
    def __str__(self):
        return self.title

    def toJson(self):
        return model_to_dict(self)

    class Meta:
        verbose_name = "Vaga"
        verbose_name_plural = "Vagas"
        db_table = "vacancy"

class JobApplication(models.Model):
    ACADEMIC_DEGREES = [
        ('ensino_medio', 'Ensino Médio'),
        ('ensino_superior', 'Ensino Superior'),
        ('mestre', 'Mestre'),
        ('doutoramento', 'Doutoramento'),
        ('mba', 'MBA'),
    ]
    
    vacancy = models.ForeignKey(JobVacancy, on_delete=models.CASCADE, related_name="applications", verbose_name="Vaga")
    full_name = models.CharField(max_length=255, verbose_name="Nome Completo")
    email = models.EmailField(verbose_name="E-mail de Contacto")
    phone = models.CharField(max_length=50, verbose_name="Número de Telemóvel")
    academic_degree = models.CharField(max_length=50, choices=ACADEMIC_DEGREES, verbose_name="Grau Académico")
    message = models.TextField(verbose_name="Mensagem", blank=True, null=True)
    cv_file = models.FileField(upload_to='recruitment/cvs/%Y/%m/%d/', verbose_name="CV")
    other_files = models.FileField(upload_to='recruitment/others/%Y/%m/%d/', blank=True, null=True, verbose_name="Outros Documentos")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.full_name} - {self.vacancy.title}"

    class Meta:
        verbose_name = "Candidatura"
        verbose_name_plural = "Candidaturas"
        db_table = "application"
