# """
# # core/timesheet/api.py
# from datetime import date, datetime, timedelta
# from typing import List
# from ninja import NinjaAPI, Router
# from ninja.pagination import paginate, PageNumberPagination
# from django.shortcuts import get_object_or_404
# from django.db.models import Sum, Q, Prefetch
# from django.contrib.auth import get_user_model
# from ninja.security import HttpBearer
#
# from .models import Timesheet, Task, Activity, Project, Department
# from .schemas import (TimesheetIn, TimesheetOut, TaskIn, TaskOut, TimesheetSummary,
#                       TimesheetStatusUpdate, ActivityOut, ProjectOut, DepartmentOut, WeeklyReport)
#
# User = get_user_model()
#
# # Configuração da API
# api = NinjaAPI(title="Timesheet System API", version="1.0.0", urls_namespace="timesheet_api")
#
#
# # Autenticação
# class AuthBearer(HttpBearer):
#     def authenticate(self, request, token):
#         # Em produção, implemente uma verificação de token real
#         if token == "secret-token":
#             return token
#
#
# # Router para timesheets
# router = Router()
#
#
# @router.post("/timesheets", response=TimesheetOut)
# def create_timesheet(request, data: TimesheetIn):
#
#     employee = get_object_or_404(User, id=data.employee_id)
#     department = get_object_or_404(Department, id=data.department_id)
#
#     # Verifica se já existe uma timesheet para este funcionário na mesma data
#     if Timesheet.objects.filter(employee=employee, date_joined=data.date_joined).exists():
#         return api.create_error_response("Já existe uma timesheet para este colaborador nesta data", status=400)
#
#     # Cria a timesheet
#     timesheet = Timesheet.objects.create(
#         employee=employee,
#         department=department,
#         date_joined=data.date_joined,
#         obs=data.obs,
#         status='rascunho'
#     )
#
#     total_hours = 0
#     # Adiciona as tarefas
#     for task_data in data.tasks:
#         activity = get_object_or_404(Activity, id=task_data.activity_id)
#         project = get_object_or_404(Project, id=task_data.project_id)
#
#         task = Task.objects.create(
#             timesheet=timesheet,
#             activity=activity,
#             project=project,
#             description=task_data.description,
#             hour_total=task_data.hour_total,
#             date_creation=task_data.date_creation
#         )
#
#         total_hours += float(task_data.hour_total)
#
#     # Atualiza o total de horas da timesheet
#     timesheet.total_hour = total_hours
#     timesheet.save()
#
#     return timesheet
#
#
# @router.get("/timesheets", response=List[TimesheetSummary])
# @paginate(PageNumberPagination)
# def list_timesheets(request, status: str = None, employee_id: int = None,
#                     start_date: date = None, end_date: date = None):
#
#     #Lista timesheets com filtros opcionais
#
#     queryset = Timesheet.objects.select_related('employee', 'department').prefetch_related('task_set')
#
#     if status:
#         queryset = queryset.filter(status=status)
#
#     if employee_id:
#         queryset = queryset.filter(employee_id=employee_id)
#
#     if start_date and end_date:
#         queryset = queryset.filter(date_joined__range=[start_date, end_date])
#
#     # Prepara resposta
#     timesheets = []
#     for ts in queryset:
#         summary = TimesheetSummary(
#             id=ts.id,
#             employee=UserOut(
#                 id=ts.employee.id,
#                 username=ts.employee.username,
#                 email=ts.employee.email,
#                 first_name=ts.employee.first_name,
#                 last_name=ts.employee.last_name
#             ),
#             department=DepartmentOut(
#                 id=ts.department.id,
#                 name=ts.department.name,
#                 description=ts.department.description
#             ),
#             status=ts.status,
#             date_joined=ts.date_joined,
#             total_hour=float(ts.total_hour) if ts.total_hour else 0,
#             task_count=ts.task_set.count()
#         )
#         timesheets.append(summary)
#
#     return timesheets
#
#
# @router.get("/timesheets/{timesheet_id}", response=TimesheetOut)
# def get_timesheet_detail(request, timesheet_id: int):
#
#     #Obtém detalhes de uma timesheet específica
#
#     timesheet = get_object_or_404(
#         Timesheet.objects.select_related('employee', 'department')
#         .prefetch_related('task_set__activity', 'task_set__project'),
#         id=timesheet_id
#     )
#     return timesheet
#
#
# @router.post("/timesheets/{timesheet_id}/tasks", response=TaskOut)
# def add_task_to_timesheet(request, timesheet_id: int, data: TaskIn):
#
#     #Adiciona uma tarefa a uma timesheet existente
#
#     timesheet = get_object_or_404(Timesheet, id=timesheet_id)
#
#     if timesheet.status != 'rascunho':
#         return api.create_error_response("Só é possível adicionar tarefas a timesheets em rascunho", status=400)
#
#     activity = get_object_or_404(Activity, id=data.activity_id)
#     project = get_object_or_404(Project, id=data.project_id)
#
#     task = Task.objects.create(
#         timesheet=timesheet,
#         activity=activity,
#         project=project,
#         description=data.description,
#         hour_total=data.hour_total,
#         date_creation=data.date_creation
#     )
#
#     # Atualiza o total de horas da timesheet
#     timesheet.total_hour = float(timesheet.total_hour or 0) + float(data.hour_total)
#     timesheet.save()
#
#     return task
#
#
# @router.put("/timesheets/{timesheet_id}/status", response=TimesheetOut)
# def update_timesheet_status(request, timesheet_id: int, data: TimesheetStatusUpdate):
#
#     #Atualiza o status de uma timesheet
#
#     timesheet = get_object_or_404(Timesheet, id=timesheet_id)
#
#     if data.status == 'submetido' and timesheet.task_set.count() == 0:
#         return api.create_error_response("Não é possível submeter uma timesheet sem tarefas", status=400)
#
#     timesheet.status = data.status
#     timesheet.save()
#
#     return timesheet
#
#
# @router.get("/activities", response=List[ActivityOut])
# def list_activities(request, department_id: int = None):
#
#    # Lista todas as atividades, opcionalmente filtradas por departamento
#
#     queryset = Activity.objects.select_related('department')
#
#     if department_id:
#         queryset = queryset.filter(department_id=department_id)
#
#     return [
#         ActivityOut(
#             id=activity.id,
#             name=activity.name,
#             description=activity.description,
#             department=DepartmentOut(
#                 id=activity.department.id,
#                 name=activity.department.name,
#                 description=activity.department.description
#             )
#         ) for activity in queryset
#     ]
#
#
# @router.get("/projects", response=List[ProjectOut])
# def list_projects(request, ativo: bool = None):
#
#     #Lista todos os projetos, opcionalmente filtrados por status ativo
#
#     queryset = Project.objects.all()
#
#     if ativo is not None:
#         queryset = queryset.filter(ativo=ativo)
#
#     return [
#         ProjectOut(
#             id=project.id,
#             name=project.name,
#             description=project.description,
#             cod_contractor=project.cod_contractor,
#             cod_supervision=project.cod_supervision,
#             cost_center=project.cost_center,
#             localization=project.localization,
#             ativo=project.ativo
#         ) for project in queryset
#     ]
#
#
# @router.get("/employees", response=List[UserOut])
# def list_employees(request):
#
#    #Lista todos os colaboradores/usuários
#
#     employees = User.objects.filter(is_active=True).order_by('first_name', 'last_name')
#     return [
#         UserOut(
#             id=user.id,
#             username=user.username,
#             email=user.email,
#             first_name=user.first_name,
#             last_name=user.last_name
#         ) for user in employees
#     ]
#
#
# @router.get("/departments", response=List[DepartmentOut])
# def list_departments(request):
#
#     #Lista todos os departamentos
#
#     departments = Department.objects.all().order_by('name')
#     return [
#         DepartmentOut(
#             id=dept.id,
#             name=dept.name,
#             description=dept.description
#         ) for dept in departments
#     ]
#
#
# @router.get("/reports/weekly", response=List[WeeklyReport])
# def weekly_report(request, start_date: date, end_date: date):
#
#    # Relatório semanal de horas por colaborador
#
#     from django.db.models import Sum
#
#     timesheets = Timesheet.objects.filter(
#         date_joined__range=[start_date, end_date],
#         status='submetido'
#     ).select_related('employee').prefetch_related('task_set__project')
#
#     # Agrupa por employee e semana
#     report_data = {}
#     for ts in timesheets:
#         employee_id = ts.employee.id
#         week_start = ts.date_joined - timedelta(days=ts.date_joined.weekday())
#
#         key = (employee_id, week_start)
#         if key not in report_data:
#             report_data[key] = {
#                 'employee': ts.employee,
#                 'week_start': week_start,
#                 'week_end': week_start + timedelta(days=6),
#                 'total_hours': 0,
#                 'projects': {}
#             }
#
#         report_data[key]['total_hours'] += float(ts.total_hour or 0)
#
#         # Contabiliza horas por projeto
#         for task in ts.task_set.all():
#             project_name = task.project.name
#             if project_name not in report_data[key]['projects']:
#                 report_data[key]['projects'][project_name] = 0
#             report_data[key]['projects'][project_name] += float(task.hour_total or 0)
#
#     # Converte para o schema de resposta
#     result = []
#     for key, data in report_data.items():
#         result.append(WeeklyReport(
#             employee=UserOut(
#                 id=data['employee'].id,
#                 username=data['employee'].username,
#                 email=data['employee'].email,
#                 first_name=data['employee'].first_name,
#                 last_name=data['employee'].last_name
#             ),
#             week_start=data['week_start'],
#             week_end=data['week_end'],
#             total_hours=data['total_hours'],
#             projects=[{"name": k, "hours": v} for k, v in data['projects'].items()]
#         ))
#
#     return result
#
#     """
# from datetime import date
# from time import timezone
# from typing import List
#
# from django.db import transaction, models
# from django.db.models import Count
# from django.shortcuts import get_object_or_404
# from django.utils import timezone
# from ninja import NinjaAPI
# from ninja.pagination import PageNumberPagination, paginate
# from ninja.security import django_auth
# from pydantic.json import Decimal
# from pydantic.utils import defaultdict
#
# from core.erp.models import Department
# from core.timesheet.models import Activity, Project, Task, Timesheet
# from core.timesheet.schemas import ActivityOut, ActivityIn, ProjectIn, ProjectOut, TimesheetIn, TimesheetOut, \
#     TimesheetUpdateIn
# from core.timesheet.utils import create_error_response
# from core.user.models import User
# from ninja.errors import HttpError, logger
#
# from . import models
# from .validators import TimesheetValidator
#
# # Configuração da API
# api = NinjaAPI(title="Timesheet System API", version="1.0.0", urls_namespace="timesheet_api", csrf=True)
#
#
# ############################### ACTIVIDADES ########################################################
#
# # @api.post("/activities")
# # def create_activitY(request, payload: ActivityIn):
# #     activity = Activity.objects.create(**payload.dict())
# #     return {"id": activity.id}
#
# @api.post("/activities")
# def create_activity(request, payload: ActivityIn):
#     activity = Activity.objects.create(
#         name=payload.name,
#         description=payload.description,
#         department_id=payload.department
#     )
#     return {"id": activity.id}
#
#
# @api.get("/activities", response=List[ActivityOut])
# def get_activities(request):
#     qs = Activity.objects.all()
#     return qs
#
#
# @api.get("/activities/{activity_id}", response=ActivityOut)
# def get_activity_by_id(request, activity_id: int):
#     activity = get_object_or_404(Activity, id=activity_id)
#     return activity
#
#
# # @api.put("/activities/{activity_id}")
# # def update_activity(request, activity_id: int, payload: ActivityIn):
# #     activity = get_object_or_404(Activity, id=activity_id)
# #     for attr, value in payload.dict().items():
# #         setattr(activity, attr, value)
# #     activity.save()
# #     return {"success": True}
#
# @api.put("/activities/{activity_id}")
# def update_activity(request, activity_id: int, payload: ActivityIn):
#     activity = get_object_or_404(Activity, id=activity_id)
#     data = payload.dict()
#
#     # trata o campo ForeignKey separadamente
#     if "department" in data:
#         activity.department_id = data.pop("department")
#
#     # atualiza os demais campos
#     for attr, value in data.items():
#         setattr(activity, attr, value)
#
#     activity.save()
#     return {"success": True}
#
#
# @api.delete("/activities/{activity_id}")
# def delete_activity(request, activity_id: int):
#     activity = get_object_or_404(Activity, id=activity_id)
#     activity.delete()
#     return {"success": True}
#
#
# ############################### PROJETOS ########################################################
#
# @api.post("/projects")
# def create_project(request, payload: ProjectIn):
#     project = Project.objects.create(**payload.dict())
#     return {"id": project.id}
#
#
# @api.get("/projects", response=List[ProjectOut])
# def get_projects(request):
#     qs = Project.objects.all()
#     return qs
#
#
# @api.get("/projects/{project_id}", response=ProjectOut)
# def get_project_by_id(request, project_id: int):
#     project = get_object_or_404(Project, id=project_id)
#     return project
#
#
# @api.put("/projects/{project_id}")
# def update_project(request, project_id: int, payload: ProjectIn):
#     project = get_object_or_404(Project, id=project_id)
#     for attr, value in payload.dict().items():
#         setattr(project, attr, value)
#     project.save()
#     return {"success": True}
#
#
# @api.delete("/projects/{project_id}")
# def delete_project(request, project_id: int):
#     project = get_object_or_404(Project, id=project_id)
#     project.delete()
#     return {"success": True}
#
#
# # ENDPOINT (como você implementou)
# # @api.post("/timesheets", response=TimesheetOut)
# # def create_timesheet(request, data: TimesheetIn):
# #     employee = get_object_or_404(User, id=data.employee_id)
# #     department = get_object_or_404(Department, id=data.department_id)
# #
# #     # Verifica se já existe uma timesheet para este funcionário na mesma data
# #     if Timesheet.objects.filter(employee=employee, date_joined=data.date_joined).exists():
# #         return create_error_response("Já existe uma timesheet para este colaborador nesta data", status=400)
# #
# #     # Cria a timesheet
# #     timesheet = Timesheet.objects.create(
# #         employee=employee,
# #         department=department,
# #         date_joined=data.date_joined,
# #         obs=data.obs,
# #         status='rascunho'
# #     )
# #
# #     total_hours = 0
# #     # Adiciona as tarefas
# #     for task_data in data.tasks:
# #         activity = get_object_or_404(Activity, id=task_data.activity_id)
# #         project = get_object_or_404(Project, id=task_data.project_id)
# #
# #         task = Task.objects.create(
# #             timesheet=timesheet,
# #             activity=activity,
# #             project=project,
# #             # description=task_data.description,
# #             hour_total=task_data.hour_total,
# #             date_creation=task_data.date_creation
# #         )
# #
# #         total_hours += float(task_data.hour_total)
# #
# #     # Atualiza o total de horas da timesheet
# #     timesheet.total_hour = total_hours
# #     timesheet.save()
# #
# #     return timesheet
#
#
# #
# # @api.get("/timesheets", response=List[TimesheetOut])
# # @paginate(PageNumberPagination)
# # def list_timesheets(request, status: str = None, employee_id: int = None,
# #                     start_date: date = None, end_date: date = None):
# #
# #     #Lista timesheets com filtros opcionais
# #
# #     queryset = Timesheet.objects.select_related('employee', 'department').prefetch_related('task_set')
# #
# #     if status:
# #         queryset = queryset.filter(status=status)
# #
# #     if employee_id:
# #         queryset = queryset.filter(employee_id=employee_id)
# #
# #     if start_date and end_date:
# #         queryset = queryset.filter(date_joined__range=[start_date, end_date])
# #
# #     # Prepara resposta
# #     timesheets = []
# #     for ts in queryset:
# #         summary = TimesheetOut(
# #             id=ts.id,
# #             employee=UserOut(
# #                 id=ts.employee.id,
# #                 username=ts.employee.username,
# #                 email=ts.employee.email,
# #                 first_name=ts.employee.first_name,
# #                 last_name=ts.employee.last_name
# #             ),
# #             department=DepartmentOut(
# #                 id=ts.department.id,
# #                 name=ts.department.name,
# #                 description=ts.department.description
# #             ),
# #             status=ts.status,
# #             date_joined=ts.date_joined,
# #             total_hour=float(ts.total_hour) if ts.total_hour else 0,
# #             task_count=ts.task_set.count()
# #         )
# #         timesheets.append(summary)
# #
# #     return timesheets
#
#
# # @api.get("/timesheets/{timesheet_id}", response=TimesheetOut)
# # def get_timesheet_detail(request, timesheet_id: int):
# #
# #     #Obtém detalhes de uma timesheet específica
# #
# #     timesheet = get_object_or_404(
# #         Timesheet.objects.select_related('employee', 'department')
# #         .prefetch_related('task_set__activity', 'task_set__project'),
# #         id=timesheet_id
# #     )
# #     return timesheet
#
#
# @api.post("/timesheets", response={200: TimesheetOut, 400: dict, 207: dict})
# def create_timesheet(request, data: TimesheetIn):
#     """
#     Cria uma nova timesheet com validação de horas por data específica
#     """
#     try:
#         # Validações iniciais
#         employee = get_object_or_404(User, id=data.employee_id)
#         department = get_object_or_404(Department, id=data.department_id)
#
#         # Verificar se employee pertence ao department
#         if employee.department_id != data.department_id:
#             raise HttpError(400, "Funcionário não pertence a este departamento")
#
#         # Validar data de criação não futura
#         if data.date_joined > timezone.now().date():
#             raise HttpError(400, "Não é possível criar timesheet para datas futuras")
#
#         # VALIDAÇÃO POR DATA ESPECÍFICA
#         daily_totals = defaultdict(Decimal)
#         daily_warnings = defaultdict(list)
#         task_dates = set()
#
#         # Calcular totais por data e verificar avisos
#         for task_data in data.tasks:
#             task_date = task_data.date_creation
#             task_hours = Decimal(str(task_data.hour_total))
#             task_dates.add(task_date)
#
#             # Soma horas por data
#             daily_totals[task_date] += task_hours
#
#             # Verifica se tarefa individual > 8h (aviso)
#             if task_hours > Decimal('8.00'):
#                 daily_warnings[task_date].append(
#                     f"Tarefa de {task_hours}h excede 8 horas no dia {task_date}"
#                 )
#
#             # Verifica se tarefa individual é válida
#             if task_hours <= Decimal('0.00'):
#                 raise HttpError(400, f"Horas da tarefa devem ser maiores que zero (dia {task_date})")
#
#         # Verificar se alguma data excede 24h
#         for task_date, total_hours in daily_totals.items():
#             if total_hours > Decimal('16.00'):
#                 raise HttpError(
#                     400,
#                     f"Total de horas no dia {task_date} é {float(total_hours)}h "
#                     f"(máximo permitido: 16h)"
#                 )
#
#         # Verificar duplicidade por data e employee
#         for task_date in task_dates:
#             if Timesheet.objects.filter(
#                     employee=employee,
#                     tasks__date_creation=task_date
#             ).exists():
#                 raise HttpError(
#                     400,
#                     f"Já existe uma timesheet para este colaborador na data {task_date}"
#                 )
#
#         # Coletar todos os avisos
#         all_warnings = []
#         for warnings in daily_warnings.values():
#             all_warnings.extend(warnings)
#
#         # Se houver avisos e não for confirmação forçada, retornar para confirmação
#         if all_warnings and not data.force_confirm:
#             return 207, {  # 207 Multi-Status
#                 "warnings": all_warnings,
#                 "requires_confirmation": True,
#                 "daily_totals": {
#                     str(date): float(total)
#                     for date, total in daily_totals.items()
#                 },
#                 "message": "Algumas tarefas excedem 8 horas. Confirme para prosseguir."
#             }
#
#         # CRIAR TIMESHEET COM TRANSAÇÃO ATÔMICA
#         with transaction.atomic():
#             # Criar timesheet
#             timesheet = Timesheet.objects.create(
#                 employee=employee,
#                 department=department,
#                 date_joined=data.date_joined,
#                 obs=data.obs,
#                 status='rascunho',
#                 total_hour=float(sum(daily_totals.values()))
#             )
#
#             # Criar tasks
#             for task_data in data.tasks:
#                 activity = get_object_or_404(Activity, id=task_data.activity_id)
#                 project = get_object_or_404(Project, id=task_data.project_id)
#
#                 Task.objects.create(
#                     timesheet=timesheet,
#                     activity=activity,
#                     project=project,
#                     hour_total=task_data.hour_total,
#                     date_creation=task_data.date_creation
#                 )
#
#         # Preparar resposta
#         response_data = {
#             "id": timesheet.id,
#             "employee_id": timesheet.employee_id,
#             "department_id": timesheet.department_id,
#             "date_joined": timesheet.date_joined,
#             "total_hour": timesheet.total_hour,
#             "obs": timesheet.obs,
#             "status": timesheet.status
#         }
#
#         # Adicionar avisos se houver
#         if all_warnings:
#             response_data["warnings"] = all_warnings
#             response_data["daily_totals"] = {
#                 str(date): float(total)
#                 for date, total in daily_totals.items()
#             }
#
#         return 200, response_data
#
#     except HttpError as e:
#         raise e
#     except Exception as e:
#         # logger.error(f"Erro ao criar timesheet: {str(e)}")
#         raise HttpError(500, f"Erro interno ao processar a solicitação: {str(e)}")
#
#
# @api.get("/timesheets/my", response=List[TimesheetOut], auth=django_auth)
# @paginate(PageNumberPagination, page_size=20)
# def my_timesheets(request):
#     """
#     Lista timesheets do usuário logado
#     """
#     queryset = Timesheet.objects.filter(
#         employee=request.user
#     ).select_related(
#         'employee', 'department'
#     ).annotate(
#         tasks_count=Count('tasks')
#     ).order_by('-date_joined')
#
#     result = []
#     for timesheet in queryset:
#         data = TimesheetOut.from_orm(timesheet)
#         data.status = timesheet.get_status_display()
#         # data.tasks_count = timesheet.tasks_count
#         # data.can_edit = timesheet.can_edit()
#         # data.can_add_task = timesheet.can_add_task()
#         result.append(data)
#
#     return result
#
#
# @api.put("/timesheets/{timesheet_id}", response={200: TimesheetOut, 400: dict, 207: dict})
# def update_timesheet(request, timesheet_id: int, data: TimesheetUpdateIn):
#     """
#     Atualiza uma timesheet existente com validação de horas por data específica
#     """
#     try:
#         # Obter timesheet existente
#         timesheet = get_object_or_404(Timesheet, id=timesheet_id)
#
#         # Validar se timesheet pode ser editada (apenas rascunho)
#         if timesheet.status != 'rascunho':
#             raise HttpError(400, "Apenas timesheets em status 'rascunho' podem ser editadas")
#
#         # Atualizar campos básicos se fornecidos
#         if data.employee_id is not None:
#             employee = get_object_or_404(User, id=data.employee_id)
#             timesheet.employee = employee
#
#         if data.department_id is not None:
#             department = get_object_or_404(Department, id=data.department_id)
#             timesheet.department = department
#
#         if data.date_joined is not None:
#             timesheet.date_joined = data.date_joined
#
#         if data.obs is not None:
#             timesheet.obs = data.obs
#
#         if data.status is not None:
#             timesheet.status = data.status
#
#         # VALIDAÇÃO POR DATA ESPECÍFICA
#         daily_totals = defaultdict(Decimal)
#         daily_warnings = defaultdict(list)
#         task_dates = set()
#
#         # Calcular totais por data das NOVAS tasks
#         for task_data in data.tasks:
#             task_date = task_data.date_creation
#             task_hours = Decimal(str(task_data.hour_total))
#             task_dates.add(task_date)
#
#             # Soma horas por data
#             daily_totals[task_date] += task_hours
#
#             # Verifica se tarefa individual > 8h (aviso)
#             if task_hours > Decimal('8.00'):
#                 daily_warnings[task_date].append(
#                     f"Tarefa de {task_hours}h excede 8 horas no dia {task_date}"
#                 )
#
#             # Verifica se tarefa individual é válida
#             if task_hours <= Decimal('0.00'):
#                 raise HttpError(400, f"Horas da tarefa devem ser maiores que zero (dia {task_date})")
#
#         # Verificar se alguma data excede 24h
#         for task_date, total_hours in daily_totals.items():
#             if total_hours > Decimal('16.00'):
#                 raise HttpError(
#                     400,
#                     f"Total de horas no dia {task_date} é {float(total_hours)}h "
#                     f"(máximo permitido: 16h)"
#                 )
#
#         # Verificar duplicidade por data e employee (excluindo a própria timesheet)
#         employee_id = data.employee_id if data.employee_id else timesheet.employee_id
#         for task_date in task_dates:
#             existing_timesheets = Timesheet.objects.filter(
#                 employee_id=employee_id,
#                 tasks__date_creation=task_date
#             ).exclude(id=timesheet_id)
#
#             if existing_timesheets.exists():
#                 raise HttpError(
#                     400,
#                     f"Já existe outra timesheet para este colaborador na data {task_date}"
#                 )
#
#         # Coletar todos os avisos
#         all_warnings = []
#         for warnings in daily_warnings.values():
#             all_warnings.extend(warnings)
#
#         # Se houver avisos e não for confirmação forçada, retornar para confirmação
#         if all_warnings and not data.force_confirm:
#             return 207, {
#                 "warnings": all_warnings,
#                 "requires_confirmation": True,
#                 "daily_totals": {
#                     str(date): float(total)
#                     for date, total in daily_totals.items()
#                 },
#                 "message": "Algumas tarefas excedem 8 horas. Confirme para prosseguir.",
#                 "timesheet_id": timesheet_id
#             }
#
#         # ATUALIZAR TIMESHEET COM TRANSAÇÃO ATÔMICA
#         with transaction.atomic():
#             # Atualizar tasks - estratégia: deletar todas e recriar
#             timesheet.tasks.all().delete()
#
#             # Criar novas tasks
#             total_hours = Decimal('0.00')
#             for task_data in data.tasks:
#                 activity = get_object_or_404(Activity, id=task_data.activity_id)
#                 project = get_object_or_404(Project, id=task_data.project_id)
#
#                 Task.objects.create(
#                     timesheet=timesheet,
#                     activity=activity,
#                     project=project,
#                     hour_total=task_data.hour_total,
#                     date_creation=task_data.date_creation
#                 )
#                 total_hours += Decimal(str(task_data.hour_total))
#
#             # Atualizar total de horas da timesheet
#             timesheet.total_hour = float(total_hours)
#             timesheet.save()
#
#         # Preparar resposta
#         response_data = {
#             "id": timesheet.id,
#             "employee_id": timesheet.employee_id,
#             "department_id": timesheet.department_id,
#             "date_joined": timesheet.date_joined,
#             "total_hour": timesheet.total_hour,
#             "obs": timesheet.obs,
#             "status": timesheet.status
#         }
#
#         # Adicionar avisos se houver
#         if all_warnings:
#             response_data["warnings"] = all_warnings
#             response_data["daily_totals"] = {
#                 str(date): float(total)
#                 for date, total in daily_totals.items()
#             }
#
#         return 200, response_data
#
#     except HttpError as e:
#         raise e
#     except Exception as e:
#         logger.error(f"Erro ao atualizar timesheet {timesheet_id}: {str(e)}")
#         raise HttpError(500, f"Erro interno ao processar a atualização: {str(e)}")
#
#
# ################################### TESTE VALIDAÇÃO SEPARADA ###########################################
#
# # #
# # @api.put("/timesheets/{timesheet_id}", response=TimesheetOut)
# # def update_timesheet2(request, timesheet_id: int, data: TimesheetIn):
# #     timesheet = get_object_or_404(Timesheet, id=timesheet_id)
# #
# #     # Atualiza dados básicos
# #     employee = get_object_or_404(User, id=data.employee_id)
# #     department = get_object_or_404(Department, id=data.department_id)
# #
# #     if Timesheet.objects.filter(
# #             employee=employee,
# #             date_joined=data.date_joined
# #     ).exclude(id=timesheet_id).exists():
# #         return create_error_response("Já existe uma timesheet para este colaborador nesta data", status=400)
# #
# #     timesheet.employee = employee
# #     timesheet.department = department
# #     timesheet.date_joined = data.date_joined
# #     timesheet.obs = data.obs
# #     timesheet.status = data.status or timesheet.status
# #     timesheet.save()
# #
# #     # Mapeia tarefas existentes
# #     existing_tasks = {task.id: task for task in Task.objects.filter(timesheet=timesheet)}
# #     received_task_ids = set()
# #
# #     total_hours = 0
# #
# #     for task_data in data.tasks:
# #         if hasattr(task_data, "id") and task_data.id in existing_tasks:
# #             # Atualiza tarefa existente
# #             task = existing_tasks[task_data.id]
# #             task.activity = get_object_or_404(Activity, id=task_data.activity_id)
# #             task.project = get_object_or_404(Project, id=task_data.project_id)
# #             task.hour_total = task_data.hour_total
# #             task.date_creation = task_data.date_creation
# #             task.save()
# #             received_task_ids.add(task.id)
# #         else:
# #             # Cria nova tarefa
# #             activity = get_object_or_404(Activity, id=task_data.activity_id)
# #             project = get_object_or_404(Project, id=task_data.project_id)
# #             task = Task.objects.create(
# #                 timesheet=timesheet,
# #                 activity=activity,
# #                 project=project,
# #                 hour_total=task_data.hour_total,
# #                 date_creation=task_data.date_creation
# #             )
# #             received_task_ids.add(task.id)
# #
# #         total_hours += float(task_data.hour_total)
# #
# #     # Remove tarefas que não foram enviadas
# #     for task_id, task in existing_tasks.items():
# #         if task_id not in received_task_ids:
# #             task.delete()
# #
# #     # Atualiza total de horas
# #     timesheet.total_hour = total_hours
# #     timesheet.save()
# #
# #     return timesheet
#
#
# ###################################################################################################
#
# @api.post("/timesheets", response={200: TimesheetOut, 400: dict, 207: dict})
# def create_timesheet1(request, data: TimesheetIn):
#     """Cria uma nova timesheet usando o validador centralizado"""
#     try:
#         # Validar dados básicos
#         employee = get_object_or_404(User, id=data.employee_id)
#         department = ""
#
#         # department = get_object_or_404(Department, id=data.department_id)
#         if hasattr(request.user, "department") and request.user.department:
#             department = request.user.department
#         # Usar validador centralizado
#         is_valid, daily_totals, warnings = TimesheetValidator.validate_timesheet_data(
#             data.dict(), employee_id=data.employee_id
#         )
#
#         # Se houver avisos e não for confirmação forçada
#         if warnings and not data.force_confirm:
#             return 207, {
#                 "warnings": warnings,
#                 "requires_confirmation": True,
#                 "daily_totals": {str(k): float(v) for k, v in daily_totals.items()},
#                 "message": "Algumas tarefas excedem 8 horas. Confirme para prosseguir."
#             }
#
#         # CRIAR TIMESHEET
#         with transaction.atomic():
#             timesheet = Timesheet.objects.create(
#                 employee=employee,
#                 department=department,
#                 date_joined=data.date_joined,
#                 obs=data.obs,
#                 status='rascunho',
#                 total_hour=float(sum(daily_totals.values()))
#             )
#
#             for task_data in data.tasks:
#                 activity = get_object_or_404(Activity, id=task_data.activity_id)
#                 project = get_object_or_404(Project, id=task_data.project_id)
#
#                 Task.objects.create(
#                     timesheet=timesheet,
#                     activity=activity,
#                     project=project,
#                     hour_total=task_data.hour_total,
#                     date_creation=task_data.date_creation
#                 )
#
#         return 200, TimesheetOut.from_orm(timesheet)
#
#     except HttpError as e:
#         raise e
#     except Exception as e:
#         raise HttpError(500, f"Erro interno: {str(e)}")
#
#
# # @api.put("/timesheets/{timesheet_id}", response={200: TimesheetOut, 400: dict, 207: dict})
# # def update_timesheet1(request, timesheet_id: int, data: TimesheetUpdateIn):
# #     """Atualiza timesheet usando validador centralizado"""
# #     try:
# #         timesheet = get_object_or_404(Timesheet, id=timesheet_id)
# #
# #         # Validações específicas de edição
# #         TimesheetValidator.validate_timesheet_status(timesheet)
# #         TimesheetValidator.validate_user_permission(timesheet, request.user)
# #
# #         # Preparar dados para validação
# #         update_data = data.dict()
# #         employee_id = update_data.get('employee_id', timesheet.employee_id)
# #
# #         # Validar com validador centralizado
# #         is_valid, daily_totals, warnings = TimesheetValidator.validate_timesheet_data(
# #             update_data, timesheet_id, employee_id
# #         )
# #
# #         # Se houver avisos e não for confirmação forçada
# #         if warnings and not data.force_confirm:
# #             return 207, {
# #                 "warnings": warnings,
# #                 "requires_confirmation": True,
# #                 "daily_totals": {str(k): float(v) for k, v in daily_totals.items()},
# #                 "message": "Algumas tarefas excedem 8 horas. Confirme para prosseguir.",
# #                 "timesheet_id": timesheet_id
# #             }
# #
# #         # ATUALIZAR TIMESHEET
# #         with transaction.atomic():
# #             # Atualizar campos básicos
# #             if data.employee_id is not None:
# #                 timesheet.employee = get_object_or_404(User, id=data.employee_id)
# #             if data.department_id is not None:
# #                 timesheet.department = get_object_or_404(Department, id=data.department_id)
# #             if data.date_joined is not None:
# #                 timesheet.date_joined = data.date_joined
# #             if data.obs is not None:
# #                 timesheet.obs = data.obs
# #             if data.status is not None:
# #                 timesheet.status = data.status
# #
# #             # Atualizar tasks
# #             timesheet.tasks.all().delete()
# #             for task_data in data.tasks:
# #                 activity = get_object_or_404(Activity, id=task_data.activity_id)
# #                 project = get_object_or_404(Project, id=task_data.project_id)
# #
# #                 Task.objects.create(
# #                     timesheet=timesheet,
# #                     activity=activity,
# #                     project=project,
# #                     hour_total=task_data.hour_total,
# #                     date_creation=task_data.date_creation
# #                 )
# #
# #             timesheet.total_hour = float(sum(daily_totals.values()))
# #             timesheet.save()
# #
# #         return 200, TimesheetOut.from_orm(timesheet)
# #
# #     except HttpError as e:
# #         raise e
# #     except Exception as e:
# #         raise HttpError(500, f"Erro interno: {str(e)}")
#
# #
# # @api.put("/timesheets/{timesheet_id}", response={200: TimesheetOut, 400: dict, 207: dict})
# # def update_timesheet1(request, timesheet_id: int, data: TimesheetUpdateIn):
# #     """Atualiza timesheet usando validador centralizado"""
# #     try:
# #         timesheet = get_object_or_404(Timesheet, id=timesheet_id)
# #
# #         # Validações específicas de edição
# #         TimesheetValidator.validate_timesheet_status(timesheet)
# #         TimesheetValidator.validate_user_permission(timesheet, request.user)
# #
# #         # Preparar dados para validação
# #         update_data = data.dict()
# #         employee_id = update_data.get('employee_id', timesheet.employee_id)
# #
# #         # Validar com validador centralizado
# #         is_valid, daily_totals, warnings = TimesheetValidator.validate_timesheet_data(
# #             update_data, timesheet_id, employee_id
# #         )
# #
# #         # Se houver avisos e não for confirmação forçada
# #         if warnings and not data.force_confirm:
# #             return 207, {
# #                 "warnings": warnings,
# #                 "requires_confirmation": True,
# #                 "daily_totals": {str(k): float(v) for k, v in daily_totals.items()},
# #                 "message": "Algumas tarefas excedem 8 horas. Confirme para prosseguir.",
# #                 "timesheet_id": timesheet_id
# #             }
# #
# #         # ATUALIZAR TIMESHEET
# #         with transaction.atomic():
# #             # Atualizar campos básicos
# #             if data.employee_id is not None:
# #                 timesheet.employee = get_object_or_404(User, id=data.employee_id)
# #             if data.department_id is not None:
# #                 timesheet.department = get_object_or_404(Department, id=data.department_id)
# #             if data.date_joined is not None:
# #                 timesheet.date_joined = data.date_joined
# #             if data.obs is not None:
# #                 timesheet.obs = data.obs
# #             if data.status is not None:
# #                 timesheet.status = data.status
# #
# #             # Atualizar tarefas
# #             existing_tasks = {task.id: task for task in timesheet.tasks.all()}
# #             incoming_ids = set()
# #
# #             for task_data in data.tasks:
# #                 if hasattr(task_data, 'id') and task_data.id in existing_tasks:
# #                     # Atualizar tarefa existente
# #                     task = existing_tasks[task_data.id]
# #                     task.project = get_object_or_404(Project, id=task_data.project_id)
# #                     task.activity = get_object_or_404(Activity, id=task_data.activity_id)
# #                     task.hour_total = task_data.hour_total
# #                     task.date_creation = task_data.date_creation
# #                     task.update_date = timezone.now()
# #                     task.save()
# #                     incoming_ids.add(task.id)
# #                 else:
# #                     # Criar nova tarefa
# #                     Task.objects.create(
# #                         timesheet=timesheet,
# #                         project=get_object_or_404(Project, id=task_data.project_id),
# #                         activity=get_object_or_404(Activity, id=task_data.activity_id),
# #                         hour_total=task_data.hour_total,
# #                         date_creation=task_data.date_creation,
# #                         update_date=timezone.now()
# #                     )
# #
# #             # Remover tarefas que não estão mais no payload
# #             for task_id, task in existing_tasks.items():
# #                 if task_id not in incoming_ids:
# #                     task.delete()
# #
# #             # Atualizar total de horas
# #             timesheet.total_hour = float(sum(daily_totals.values()))
# #             timesheet.update_date = timezone.now()
# #             timesheet.save()
# #
# #         return 200, TimesheetOut.from_orm(timesheet)
# #
# #     except HttpError as e:
# #         raise e
# #     except Exception as e:
# #         raise HttpError(500, f"Erro interno: {str(e)}")
# #
# # @api.put("/timesheets/{timesheet_id}", response={200: TimesheetOut, 400: dict, 207: dict})
# # def update_timesheet1(request, timesheet_id: int, data: TimesheetUpdateIn):
# #     """Atualiza timesheet usando validador centralizado"""
# #     import logging
# #     logger = logging.getLogger(__name__)
# #
# #     try:
# #         timesheet = get_object_or_404(Timesheet, id=timesheet_id)
# #
# #         # Validações específicas de edição
# #         TimesheetValidator.validate_timesheet_status(timesheet)
# #         TimesheetValidator.validate_user_permission(timesheet, request.user)
# #
# #         # Preparar dados para validação - converter para dict
# #         update_data = data.dict()
# #         employee_id = update_data.get('employee_id', timesheet.employee_id)
# #
# #         # Validar com validador centralizado
# #         is_valid, daily_totals, warnings = TimesheetValidator.validate_timesheet_data(
# #             update_data, timesheet_id, employee_id
# #         )
# #
# #         # Se houver avisos e não for confirmação forçada
# #         if warnings and not data.force_confirm:
# #             return 207, {
# #                 "warnings": warnings,
# #                 "requires_confirmation": True,
# #                 "daily_totals": {str(k): float(v) for k, v in daily_totals.items()},
# #                 "message": "Algumas tarefas excedem 8 horas. Confirme para prosseguir.",
# #                 "timesheet_id": timesheet_id
# #             }
# #
# #         # ATUALIZAR TIMESHEET
# #         with transaction.atomic():
# #             # Atualizar campos básicos
# #             if data.employee_id is not None:
# #                 timesheet.employee = get_object_or_404(User, id=data.employee_id)
# #             if data.department_id is not None:
# #                 timesheet.department = get_object_or_404(Department, id=data.department_id)
# #             if data.date_joined is not None:
# #                 timesheet.date_joined = data.date_joined
# #             if data.obs is not None:
# #                 timesheet.obs = data.obs
# #             if data.status is not None:
# #                 timesheet.status = data.status
# #
# #             # Verificar tarefas existentes
# #             existing_tasks = {task.id: task for task in timesheet.tasks.all()}
# #             logger.debug(f"Tarefas existentes na timesheet {timesheet_id}: {list(existing_tasks.keys())}")
# #
# #             incoming_ids = set()
# #
# #             for task_data in data.tasks:
# #                 # Converter task_data.id para int para garantir comparação correta
# #                 task_id = None
# #                 if task_data.id is not None:
# #                     try:
# #                         # Garantir que seja um número válido
# #                         if isinstance(task_data.id, str) and task_data.id.isdigit():
# #                             task_id = int(task_data.id)
# #                         elif isinstance(task_data.id, int) and task_data.id > 0:
# #                             task_id = task_data.id
# #                     except (ValueError, TypeError):
# #                         task_id = None
# #
# #                 logger.debug(
# #                     f"Tarefa recebida - ID original: {task_data.id}, ID convertido: {task_id}, Existing keys: {list(existing_tasks.keys())}")
# #
# #                 # Verificar se é tarefa existente (ID válido e existe na base)
# #                 if task_id and task_id in existing_tasks:
# #                     logger.debug(f"✅ Atualizando tarefa existente ID {task_id}")
# #                     # Atualizar tarefa existente (mantém o mesmo ID)
# #                     task = existing_tasks[task_id]
# #                     task.project = get_object_or_404(Project, id=task_data.project_id)
# #                     task.activity = get_object_or_404(Activity, id=task_data.activity_id)
# #                     task.hour_total = task_data.hour_total
# #                     task.date_creation = task_data.date_creation
# #                     task.update_date = timezone.now()
# #                     task.save()
# #                     incoming_ids.add(task.id)  # Mantém o ID original
# #                     logger.debug(f"✅ Tarefa {task.id} atualizada com sucesso - ID mantido")
# #                 else:
# #                     logger.debug(f"➕ Criando nova tarefa (ID recebido: {task_data.id})")
# #                     # Criar nova tarefa (ID None, 0, inválido ou não existe)
# #                     new_task = Task.objects.create(
# #                         timesheet=timesheet,
# #                         project=get_object_or_404(Project, id=task_data.project_id),
# #                         activity=get_object_or_404(Activity, id=task_data.activity_id),
# #                         hour_total=task_data.hour_total,
# #                         date_creation=task_data.date_creation,
# #                         update_date=timezone.now()
# #                     )
# #                     incoming_ids.add(new_task.id)  # Novo ID apenas para tarefas novas
# #                     logger.debug(f"➕ Nova tarefa criada com ID {new_task.id}")
# #
# #             logger.debug(f"IDs que permanecem após processamento: {incoming_ids}")
# #
# #             # Remover tarefas que não estão mais no payload
# #             tasks_to_delete = []
# #             for task_id, task in existing_tasks.items():
# #                 if task_id not in incoming_ids:
# #                     logger.debug(f"🗑️ Marcando para deletar tarefa ID {task_id}")
# #                     tasks_to_delete.append(task)
# #
# #             # Deletar em lote para melhor performance
# #             if tasks_to_delete:
# #                 Task.objects.filter(id__in=[task.id for task in tasks_to_delete]).delete()
# #                 logger.debug(f"🗑️ Deletadas {len(tasks_to_delete)} tarefas")
# #
# #             # Recalcular total de horas baseado nas tarefas atuais
# #             # (corrige a inconsistência de usar daily_totals calculado antes da transação)
# #             total_hours = timesheet.tasks.aggregate(
# #                 total=models.Sum('hour_total')
# #             )['total'] or 0
# #
# #             timesheet.total_hour = float(total_hours)
# #             timesheet.update_date = timezone.now()
# #             timesheet.save()
# #
# #             logger.debug(f"✅ Timesheet atualizada - Total de horas: {timesheet.total_hour}")
# #
# #         return 200, TimesheetOut.from_orm(timesheet)
# #
# #     except HttpError as e:
# #         raise e
# #     except Exception as e:
# #         logger.error(f"Erro interno ao atualizar timesheet {timesheet_id}: {str(e)}")
# #         raise HttpError(500, f"Erro interno: {str(e)}")
#
#
# @api.put("/timesheets/{timesheet_id}", response={200: dict, 400: dict, 207: dict})
# def update_timesheet11(request, timesheet_id: int, data: TimesheetUpdateIn):
#     """Atualiza timesheet usando validador centralizado - COM DEBUG"""
#     try:
#         timesheet = get_object_or_404(Timesheet, id=timesheet_id)
#
#         # Validações específicas de edição
#         TimesheetValidator.validate_timesheet_status(timesheet)
#         TimesheetValidator.validate_user_permission(timesheet, request.user)
#
#         # Preparar dados para validação - converter para dict
#         update_data = data.dict()
#         employee_id = update_data.get('employee_id', timesheet.employee_id)
#
#         # Validar com validador centralizado
#         is_valid, daily_totals, warnings = TimesheetValidator.validate_timesheet_data(
#             update_data, timesheet_id, employee_id
#         )
#
#         # Se houver avisos e não for confirmação forçada
#         if warnings and not data.force_confirm:
#             return 207, {
#                 "warnings": warnings,
#                 "requires_confirmation": True,
#                 "daily_totals": {str(k): float(v) for k, v in daily_totals.items()},
#                 "message": "Algumas tarefas excedem 8 horas. Confirme for prosseguir.",
#                 "timesheet_id": timesheet_id
#             }
#
#         # VARIÁVEL PARA DEBUG
#         debug_info = {
#             "existing_tasks_before": [],
#             "task_processing": [],
#             "incoming_ids": [],
#             "tasks_to_delete": [],
#             "final_total": 0
#         }
#
#         # ATUALIZAR TIMESHEET
#         with transaction.atomic():
#             # Atualizar campos básicos
#             if data.employee_id is not None:
#                 timesheet.employee = get_object_or_404(User, id=data.employee_id)
#             if data.department_id is not None:
#                 timesheet.department = get_object_or_404(Department, id=data.department_id)
#             if data.date_joined is not None:
#                 timesheet.date_joined = data.date_joined
#             if data.obs is not None:
#                 timesheet.obs = data.obs
#             if data.status is not None:
#                 timesheet.status = data.status
#
#             # Verificar tarefas existentes
#             existing_tasks_queryset = timesheet.tasks.all()
#             existing_tasks = {task.id: task for task in existing_tasks_queryset}
#
#             # DEBUG: Capturar info das tarefas existentes
#             debug_info["existing_tasks_before"] = [
#                 {
#                     "id": task.id,
#                     "type": str(type(task.id)),
#                     "project_id": task.project_id,
#                     "activity_id": task.activity_id,
#                     "hour_total": float(task.hour_total)
#                 }
#                 for task in existing_tasks_queryset
#             ]
#
#             incoming_ids = set()
#
#             for task_data in data.tasks:
#                 # Informações de debug para esta tarefa
#                 task_debug = {
#                     "received_id": task_data.id,
#                     "received_id_type": str(type(task_data.id)),
#                     "converted_id": None,
#                     "action": None,
#                     "final_id": None
#                 }
#
#                 # Converter task_data.id para int para garantir comparação correta
#                 task_id = None
#                 if task_data.id is not None:
#                     try:
#                         if isinstance(task_data.id, str) and task_data.id.isdigit():
#                             task_id = int(task_data.id)
#                         elif isinstance(task_data.id, int) and task_data.id > 0:
#                             task_id = task_data.id
#                     except (ValueError, TypeError):
#                         task_id = None
#
#                 task_debug["converted_id"] = task_id
#                 task_debug["exists_in_db"] = task_id in existing_tasks if task_id else False
#
#                 # Verificar se é tarefa existente
#                 if task_id and task_id in existing_tasks:
#                     task_debug["action"] = "UPDATE_EXISTING"
#                     # Atualizar tarefa existente (mantém o mesmo ID)
#                     task = existing_tasks[task_id]
#                     task.project = get_object_or_404(Project, id=task_data.project_id)
#                     task.activity = get_object_or_404(Activity, id=task_data.activity_id)
#                     task.hour_total = task_data.hour_total
#                     task.date_creation = task_data.date_creation
#                     task.update_date = timezone.now()
#                     task.save()
#                     incoming_ids.add(task.id)
#                     task_debug["final_id"] = task.id
#                 else:
#                     task_debug["action"] = "CREATE_NEW"
#                     # Criar nova tarefa
#                     new_task = Task.objects.create(
#                         timesheet=timesheet,
#                         project=get_object_or_404(Project, id=task_data.project_id),
#                         activity=get_object_or_404(Activity, id=task_data.activity_id),
#                         hour_total=task_data.hour_total,
#                         date_creation=task_data.date_creation,
#                         update_date=timezone.now()
#                     )
#                     incoming_ids.add(new_task.id)
#                     task_debug["final_id"] = new_task.id
#
#                 debug_info["task_processing"].append(task_debug)
#
#             debug_info["incoming_ids"] = list(incoming_ids)
#
#             # Remover tarefas que não estão mais no payload
#             tasks_to_delete = []
#             for task_id, task in existing_tasks.items():
#                 if task_id not in incoming_ids:
#                     tasks_to_delete.append({
#                         "id": task_id,
#                         "project_id": task.project_id,
#                         "will_be_deleted": True
#                     })
#                     task.delete()
#
#             debug_info["tasks_to_delete"] = tasks_to_delete
#
#             # Recalcular total de horas
#             total_hours = timesheet.tasks.aggregate(
#                 total=models.Sum('hour_total')
#             )['total'] or 0
#
#             timesheet.total_hour = float(total_hours)
#             debug_info["final_total"] = float(total_hours)
#             timesheet.update_date = timezone.now()
#             timesheet.save()
#
#         # Retornar com informações de debug
#         return 200, {
#             "timesheet": TimesheetOut.from_orm(timesheet).dict(),
#             "debug_info": debug_info,
#             "message": "Timesheet atualizada com sucesso - DEBUG ATIVO"
#         }
#
#     except HttpError as e:
#         raise e
#     except Exception as e:
#         return 400, {
#             "error": f"Erro interno: {str(e)}",
#             "debug_info": debug_info if 'debug_info' in locals() else {}
#         }
#
#
# @api.put("/timesheets/{timesheet_id}", response={200: TimesheetOut, 400: dict, 207: dict})
# def update_timesheet12(request, timesheet_id: int, data: TimesheetUpdateIn):
#     """Atualiza timesheet - VERSÃO SIMPLIFICADA"""
#     try:
#         timesheet = get_object_or_404(Timesheet, id=timesheet_id)
#
#         # Validações específicas de edição
#         TimesheetValidator.validate_timesheet_status(timesheet)
#         TimesheetValidator.validate_user_permission(timesheet, request.user)
#
#         # Preparar dados para validação
#         update_data = data.dict()
#         employee_id = update_data.get('employee_id', timesheet.employee_id)
#
#         # Validar com validador centralizado
#         is_valid, daily_totals, warnings = TimesheetValidator.validate_timesheet_data(
#             update_data, timesheet_id, employee_id
#         )
#
#         # Se houver avisos e não for confirmação forçada
#         if warnings and not data.force_confirm:
#             return 207, {
#                 "warnings": warnings,
#                 "requires_confirmation": True,
#                 "daily_totals": {str(k): float(v) for k, v in daily_totals.items()},
#                 "message": "Algumas tarefas excedem 8 horas. Confirme para prosseguir.",
#                 "timesheet_id": timesheet_id
#             }
#
#         # ATUALIZAR TIMESHEET
#         with transaction.atomic():
#             # Atualizar campos básicos do timesheet
#             if data.employee_id is not None:
#                 timesheet.employee = get_object_or_404(User, id=data.employee_id)
#             if data.department_id is not None:
#                 timesheet.department = get_object_or_404(Department, id=data.department_id)
#             if data.date_joined is not None:
#                 timesheet.date_joined = data.date_joined
#             if data.obs is not None:
#                 timesheet.obs = data.obs
#             if data.status is not None:
#                 timesheet.status = data.status
#
#             # ESTRATÉGIA SIMPLES: Separar por ação clara
#             tasks_to_update = []  # Tarefas com ID válido para atualizar
#             tasks_to_create = []  # Tarefas sem ID ou ID inválido para criar
#
#             # Separar tarefas por ação
#             for task_data in data.tasks:
#                 # Se tem ID válido (não None, não 0, é número)
#                 if (task_data.id is not None and
#                         (isinstance(task_data.id, int) and task_data.id > 0) or
#                         (isinstance(task_data.id, str) and task_data.id.isdigit() and int(task_data.id) > 0)):
#
#                     # Tentar converter para int se for string
#                     if isinstance(task_data.id, str):
#                         task_id = int(task_data.id)
#                     else:
#                         task_id = task_data.id
#
#                     tasks_to_update.append((task_id, task_data))
#                 else:
#                     # ID None, 0 ou inválido = criar nova
#                     tasks_to_create.append(task_data)
#
#             # PROCESSAR ATUALIZAÇÕES (manter IDs existentes)
#             updated_ids = set()
#             for task_id, task_data in tasks_to_update:
#                 try:
#                     # Buscar a tarefa existente
#                     existing_task = Task.objects.get(id=task_id, timesheet=timesheet)
#
#                     # Atualizar campos
#                     existing_task.project = get_object_or_404(Project, id=task_data.project_id)
#                     existing_task.activity = get_object_or_404(Activity, id=task_data.activity_id)
#                     existing_task.hour_total = task_data.hour_total
#                     existing_task.date_creation = task_data.date_creation
#                     existing_task.update_date = timezone.now()
#                     existing_task.save()
#
#                     updated_ids.add(task_id)
#
#                 except Task.DoesNotExist:
#                     # Se não existe, criar como nova (fallback)
#                     new_task = Task.objects.create(
#                         timesheet=timesheet,
#                         project=get_object_or_404(Project, id=task_data.project_id),
#                         activity=get_object_or_404(Activity, id=task_data.activity_id),
#                         hour_total=task_data.hour_total,
#                         date_creation=task_data.date_creation,
#                         update_date=timezone.now()
#                     )
#                     updated_ids.add(new_task.id)
#
#             # PROCESSAR CRIAÇÕES (novos IDs)
#             for task_data in tasks_to_create:
#                 new_task = Task.objects.create(
#                     timesheet=timesheet,
#                     project=get_object_or_404(Project, id=task_data.project_id),
#                     activity=get_object_or_404(Activity, id=task_data.activity_id),
#                     hour_total=task_data.hour_total,
#                     date_creation=task_data.date_creation,
#                     update_date=timezone.now()
#                 )
#                 updated_ids.add(new_task.id)
#
#             # DELETAR tarefas que não estão mais no payload
#             Task.objects.filter(
#                 timesheet=timesheet
#             ).exclude(
#                 id__in=updated_ids
#             ).delete()
#
#             # Recalcular total de horas
#             total_hours = Task.objects.filter(
#                 timesheet=timesheet
#             ).aggregate(
#                 total=models.Sum('hour_total')
#             )['total'] or 0
#
#             timesheet.total_hour = float(total_hours)
#             timesheet.update_date = timezone.now()
#             timesheet.save()
#
#         return 200, TimesheetOut.from_orm(timesheet)
#
#     except HttpError as e:
#         raise e
#     except Exception as e:
#         raise HttpError(500, f"Erro interno: {str(e)}")
#
#
# @api.put("/timesheets/{timesheet_id}", response={200: TimesheetOut, 400: dict, 207: dict})
# def update_timesheet1(request, timesheet_id: int, data: TimesheetUpdateIn):
#     """Atualiza timesheet - VERSÃO REFACTORIZADA COM EXCLUSÃO EXPLÍCITA"""
#     try:
#         timesheet = get_object_or_404(Timesheet, id=timesheet_id)
#
#         # Validações específicas de edição
#         TimesheetValidator.validate_timesheet_status(timesheet)
#         TimesheetValidator.validate_user_permission(timesheet, request.user)
#
#         # Preparar dados para validação
#         update_data = data.dict()
#         employee_id = update_data.get('employee_id', timesheet.employee_id)
#
#         # Validar com validador centralizado
#         is_valid, daily_totals, warnings = TimesheetValidator.validate_timesheet_data(
#             update_data, timesheet_id, employee_id
#         )
#
#         if warnings and not data.force_confirm:
#             return 207, {
#                 "warnings": warnings,
#                 "requires_confirmation": True,
#                 "daily_totals": {str(k): float(v) for k, v in daily_totals.items()},
#                 "message": "Algumas tarefas excedem 8 horas. Confirme para prosseguir.",
#                 "timesheet_id": timesheet_id
#             }
#
#         with transaction.atomic():
#             # Atualizar campos básicos
#             if data.employee_id is not None:
#                 timesheet.employee = get_object_or_404(User, id=data.employee_id)
#
#             # Obter departamento do usuário autenticado
#             if hasattr(request.user, "department") and request.user.department:
#                 timesheet.department = request.user.department
#
#             if data.date_joined is not None:
#                 timesheet.date_joined = data.date_joined
#             if data.obs is not None:
#                 timesheet.obs = data.obs
#             if data.status is not None:
#                 timesheet.status = data.status
#
#             tasks_to_update = []
#             tasks_to_create = []
#
#             for task_data in data.tasks:
#                 if (task_data.id is not None and
#                         (isinstance(task_data.id, int) and task_data.id > 0) or
#                         (isinstance(task_data.id, str) and task_data.id.isdigit() and int(task_data.id) > 0)):
#
#                     task_id = int(task_data.id) if isinstance(task_data.id, str) else task_data.id
#                     tasks_to_update.append((task_id, task_data))
#                 else:
#                     tasks_to_create.append(task_data)
#
#             updated_ids = set()
#             for task_id, task_data in tasks_to_update:
#                 try:
#                     existing_task = Task.objects.get(id=task_id, timesheet=timesheet)
#                     existing_task.project = get_object_or_404(Project, id=task_data.project_id)
#                     existing_task.activity = get_object_or_404(Activity, id=task_data.activity_id)
#                     existing_task.hour_total = task_data.hour_total
#                     existing_task.date_creation = task_data.date_creation
#                     existing_task.update_date = timezone.now()
#                     existing_task.save()
#                     updated_ids.add(task_id)
#                 except Task.DoesNotExist:
#                     new_task = Task.objects.create(
#                         timesheet=timesheet,
#                         project=get_object_or_404(Project, id=task_data.project_id),
#                         activity=get_object_or_404(Activity, id=task_data.activity_id),
#                         hour_total=task_data.hour_total,
#                         date_creation=task_data.date_creation,
#                         update_date=timezone.now()
#                     )
#                     updated_ids.add(new_task.id)
#
#             for task_data in tasks_to_create:
#                 new_task = Task.objects.create(
#                     timesheet=timesheet,
#                     project=get_object_or_404(Project, id=task_data.project_id),
#                     activity=get_object_or_404(Activity, id=task_data.activity_id),
#                     hour_total=task_data.hour_total,
#                     date_creation=task_data.date_creation,
#                     update_date=timezone.now()
#                 )
#                 updated_ids.add(new_task.id)
#
#             # Exclusão explícita de tarefas
#             if data.deleted_task_ids:
#                 Task.objects.filter(
#                     timesheet=timesheet,
#                     id__in=data.deleted_task_ids
#                 ).delete()
#
#             # Recalcular total de horas
#             total_hours = Task.objects.filter(
#                 timesheet=timesheet
#             ).aggregate(
#                 total=models.Sum('hour_total')
#             )['total'] or 0
#
#             timesheet.total_hour = float(total_hours)
#             timesheet.update_date = timezone.now()
#             timesheet.save()
#
#         return 200, TimesheetOut.from_orm(timesheet)
#
#     except HttpError as e:
#         raise e
#     except Exception as e:
#         raise HttpError(500, f"Erro interno: {str(e)}")
#
# # @api.get("/me", response=UserOut)
# # def get_current_user(request):
# #     user = request.user
# #     return UserOut(
# #         id=user.id,
# #         username=user.username,
# #         email=user.email,
# #         first_name=user.first_name,
# #         last_name=user.last_name,
# #         full_name=user.get_full_name(),  # Aqui é onde calculas
# #         image=user.get_image(),
# #         date_joined=user.date_joined,
# #         last_login=user.last_login,
# #         department=user.department.toJson() if user.department else None,
# #         position=user.position.toJson() if user.position else None,
# #         groups=[{"id": g.id, "name": g.name} for g in user.groups.all()]
# #     )
