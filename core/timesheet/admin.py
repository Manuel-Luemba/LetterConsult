# from django.contrib import admin
#
# from core.timesheet.models import Activity, Task, Project, Timesheet
#
#
# class TaskInline(admin.TabularInline):
#     model = Task
#     extra = 1
#     fields = ['activity', 'project' 'hour_total', 'day_status']
#
#
# @admin.register(Timesheet)
# class TimesheetAdmin(admin.ModelAdmin):
#     inlines = [TaskInline]
#     list_display = ('__str__', 'employee', 'creation_date', 'total_hour')
#     search_fields = ('employee__username', 'date_creation',)
#     date_hierarchy = 'creation_date'
#     ordering = ('-creation_date',)
#
#
# @admin.register(Task)
# class TaskAdmin(admin.ModelAdmin):
#     list_display = ['activity', 'project', 'hour_start', 'hour_end', 'hour_total', 'day_status']
#
#
#
