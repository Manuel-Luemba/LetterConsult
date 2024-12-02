from datetime import date, timedelta

from django.test import TestCase

from core.erp import models
from core.erp.models import Notification


# Listar
# select * from Tabela
# query = Department.objects.all()
# print(query)

# Inserção
# dept = DEPARTMENT()
# dept.name = 'Jurídico'
# dept.description = 'A department'
# dept.save()

# Modificação
# dept = DEPARTMENT.objects.get(id=2)
# print(dept.name)
# dept.description = 'Cuidamos do Pessoal da empresa'
# dept.save()

# Eliminar
# try:
# dept = DEPARTMENT.objects.get(pk=4)
# dept.delete()
# except Exception as e:
# print(e)

# Filtros
# emp = Employee.objects.filter()

# dept = DEPARTMENT.objects.filter(name__icontains="a").exclude(id=2)
# print(dept)
