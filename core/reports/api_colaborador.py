# # dashboard/colaborador/views.py
# from datetime import timedelta
# from decimal import Decimal
# from django.utils import timezone
# from django.db.models import Sum, Count, Avg, Q
# from ninja import Router
# from ninja.pagination import paginate, PageNumberPagination
# from ninja.errors import HttpError
#
# from timesheet.models import Task, Timesheet, Project, Activity
# from dashboard.base.permissions import UserRole, require_role
# from dashboard.base.filters import apply_task_filters, fill_missing_dates
# from dashboard.base.metrics import calculate_kpis, calculate_daily_hours, calculate_project_hours
# from dashboard.schemas import (
#     DashboardFilterSchema,
#     ColaboradorKPISchema,
#     ColaboradorDashboardSchema,
#     FilteredDashboardResponseSchema,
#     DailyHoursSchema,
#     ProjectHoursSchema,
#     TaskSimpleSchema,
#     TimesheetSimpleSchema,
#     FilterOptionsSchema
# )
#
# router = Router(tags=["Dashboard Colaborador"])
#
#
# # DECORATOR GLOBAL: Só colaboradores podem acessar este router
# @router.middleware
# def check_colaborador_access(request, call_next):
#     """Middleware para verificar se é colaborador"""
#     user = request.auth
#     role = UserRole.get_role(user)
#
#     if role != "colaborador":
#         raise PermissionDenied("Este dashboard é apenas para colaboradores")
#
#     return call_next(request)
#
#
# @router.post("/kpis/", response=ColaboradorKPISchema)
# @require_role(["colaborador"])
# def get_colaborador_kpis(request, filters: DashboardFilterSchema):
#     """KPIs pessoais do colaborador - APENAS SEUS DADOS"""
#     user = request.auth
#
#     # GARANTIA: Sempre filtra pelo próprio usuário
#     base_qs = Task.objects.filter(timesheet__employee=user)
#
#     # Remover qualquer tentativa de filtrar por outros funcionários
#     if hasattr(filters, 'funcionario_id'):
#         filters.funcionario_id = None
#
#     filtered_qs, date_range = apply_task_filters(base_qs, user, filters.dict())
#
#     # Calcular KPIs
#     kpis = calculate_kpis(filtered_qs, user, date_range)
#
#     return kpis
#
#
# @router.post("/daily-hours/", response=List[DailyHoursSchema])
# @require_role(["colaborador"])
# def get_colaborador_daily_hours(request, filters: DashboardFilterSchema):
#     """Horas diárias do colaborador - APENAS SEUS DADOS"""
#     user = request.auth
#
#     # GARANTIA: Sempre filtra pelo próprio usuário
#     base_qs = Task.objects.filter(timesheet__employee=user)
#     filtered_qs, date_range = apply_task_filters(base_qs, user, filters.dict())
#
#     daily_data = calculate_daily_hours(filtered_qs, date_range)
#
#     # Preencher dias faltantes
#     return fill_missing_dates(daily_data, date_range)
#
#
# @router.post("/project-hours/", response=List[ProjectHoursSchema])
# @require_role(["colaborador"])
# def get_colaborador_project_hours(request, filters: DashboardFilterSchema):
#     """Distribuição por projeto do colaborador - APENAS SEUS DADOS"""
#     user = request.auth
#
#     # GARANTIA: Sempre filtra pelo próprio usuário
#     base_qs = Task.objects.filter(timesheet__employee=user)
#     filtered_qs, _ = apply_task_filters(base_qs, user, filters.dict())
#
#     return calculate_project_hours(filtered_qs)
#
#
# @router.post("/recent-tasks/", response=List[TaskSimpleSchema])
# @paginate(PageNumberPagination, page_size=10)
# @require_role(["colaborador"])
# def get_colaborador_recent_tasks(request, filters: DashboardFilterSchema):
#     """Tarefas recentes do colaborador - APENAS SEUS DADOS"""
#     user = request.auth
#
#     # GARANTIA: Sempre filtra pelo próprio usuário
#     base_qs = Task.objects.filter(timesheet__employee=user)
#     filtered_qs, _ = apply_task_filters(base_qs, user, filters.dict())
#
#     tasks = filtered_qs.select_related('project', 'activity').order_by('-created_at')
#
#     return [
#         {
#             "id": task.id,
#             "project_name": task.project.name if task.project else None,
#             "activity_name": task.activity.name if task.activity else None,
#             "hour": task.hour,
#             "created_at": task.created_at.date()
#         }
#         for task in tasks
#     ]
#
#
# @router.post("/recent-timesheets/", response=List[TimesheetSimpleSchema])
# @paginate(PageNumberPagination, page_size=5)
# @require_role(["colaborador"])
# def get_colaborador_recent_timesheets(request, filters: DashboardFilterSchema):
#     """Timesheets recentes do colaborador - APENAS SEUS DADOS"""
#     user = request.auth
#
#     date_range = filters.get_date_range()
#
#     # GARANTIA: Sempre filtra pelo próprio usuário
#     timesheets = Timesheet.objects.filter(
#         employee=user,
#         created_at__date__gte=date_range['start_date'],
#         created_at__date__lte=date_range['end_date']
#     ).order_by('-created_at')
#
#     if filters.status:
#         timesheets = timesheets.filter(status=filters.status)
#
#     return [
#         {
#             "id": ts.id,
#             "status": ts.status,
#             "total_hour": ts.total_hour,
#             "created_at": ts.created_at.date(),
#             "submitted_at": ts.submitted_at.date() if ts.submitted_at else None,
#             "updated_at": ts.updated_at.date() if ts.updated_at else None,
#             "obs": ts.obs,
#             "employee_name": user.get_full_name(),
#             "department_name": user.department.name if user.department else None
#         }
#         for ts in timesheets
#     ]
#
#
# @router.post("/full-dashboard/", response=FilteredDashboardResponseSchema)
# @require_role(["colaborador"])
# def get_colaborador_full_dashboard(request, filters: DashboardFilterSchema):
#     """Dashboard completo do colaborador - APENAS SEUS DADOS"""
#     user = request.auth
#
#     # Coletar todos os dados (já filtrados pelo usuário)
#     kpis = get_colaborador_kpis(request, filters)
#     daily_hours = get_colaborador_daily_hours(request, filters)
#     project_hours = get_colaborador_project_hours(request, filters)
#
#     # Tarefas recentes
#     recent_tasks = Task.objects.filter(
#         timesheet__employee=user
#     ).select_related('project', 'activity').order_by('-created_at')[:10]
#
#     tasks_list = [
#         {
#             "id": task.id,
#             "project_name": task.project.name if task.project else None,
#             "activity_name": task.activity.name if task.activity else None,
#             "hour": task.hour,
#             "created_at": task.created_at.date()
#         }
#         for task in recent_tasks
#     ]
#
#     # Timesheets recentes
#     recent_timesheets = Timesheet.objects.filter(
#         employee=user
#     ).order_by('-created_at')[:5]
#
#     timesheets_list = [
#         {
#             "id": ts.id,
#             "status": ts.status,
#             "total_hour": ts.total_hour,
#             "created_at": ts.created_at.date(),
#             "submitted_at": ts.submitted_at.date() if ts.submitted_at else None,
#             "updated_at": ts.updated_at.date() if ts.updated_at else None,
#             "obs": ts.obs,
#             "employee_name": user.get_full_name(),
#             "department_name": user.department.name if user.department else None
#         }
#         for ts in recent_timesheets
#     ]
#
#     date_range = filters.get_date_range()
#
#     return {
#         "kpis": kpis,
#         "daily_hours": daily_hours,
#         "project_hours": project_hours,
#         "recent_tasks": tasks_list,
#         "recent_timesheets": timesheets_list,
#         "filters_applied": filters,
#         "date_range": date_range
#     }
#
#
# @router.get("/filter-options/", response=FilterOptionsSchema)
# @require_role(["colaborador"])
# def get_colaborador_filter_options(request):
#     """Opções de filtro para o colaborador - APENAS SEUS DADOS"""
#     user = request.auth
#
#     # Projetos do colaborador
#     projetos = Project.objects.filter(
#         task__timesheet__employee=user
#     ).distinct().values('id', 'name').order_by('name')
#
#     # Atividades do colaborador
#     atividades = Activity.objects.filter(
#         task__timesheet__employee=user
#     ).distinct().values('id', 'name').order_by('name')
#
#     # Opções de status
#     status_options = [
#         {"value": "rascunho", "label": "Rascunho"},
#         {"value": "submetido", "label": "Submetido"},
#         {"value": "aprovado", "label": "Aprovado"},
#         {"value": "rejeitado", "label": "Rejeitado"},
#     ]
#
#     # Opções de período
#     period_options = [
#         {"value": "week", "label": "Esta Semana"},
#         {"value": "month", "label": "Este Mês"},
#         {"value": "quarter", "label": "Este Trimestre"},
#         {"value": "year", "label": "Este Ano"},
#         {"value": "custom", "label": "Personalizado"},
#     ]
#
#     return {
#         "projects": list(projetos),
#         "activities": list(atividades),
#         "status_options": status_options,
#         "period_options": period_options
#     }