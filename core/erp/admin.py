from django.contrib import admin

from core.activity.models import Activity
# Register your models here.

from core.erp.models import Department, Reference
from core.homepage.models import Position
from core.project.models import Project
from core.timesheet.models import Task, Timesheet

# Register your models here.
admin.site.register(Department)
admin.site.register(Reference)
admin.site.register(Position)

admin.site.register(Activity)
admin.site.register(Project)
# admin.site.register(Timesheet)


class TaskInline(admin.TabularInline):  # ou admin.StackedInline se preferires
    model = Task
    extra = 1  # número de linhas vazias para adicionar
    fields = ('project', 'activity', 'hour_total', 'created_at')
    #autocomplete_fields = ('project', 'activity')  # se estiveres a usar autocomplete
    show_change_link = True


@admin.register(Timesheet)
class TimesheetAdmin(admin.ModelAdmin):
    list_display = ('employee', 'status', 'total_hour', 'created_at')
    inlines = [TaskInline]
    #search_fields = ('employee__username', 'department__name')
    #list_filter = ('status', 'department')
