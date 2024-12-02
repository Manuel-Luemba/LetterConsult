from django.contrib import admin

# Register your models here.

from core.erp.models import Department, Reference
from core.homepage.models import Absence

# Register your models here.
admin.site.register(Department)
admin.site.register(Absence)
admin.site.register(Reference)
