from datetime import datetime
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.urls import reverse_lazy
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import ListView, CreateView, DeleteView
from django.utils.decorators import method_decorator
from app.util import enviar_email_referencia
from core.erp.forms import ReferenceForm
from core.erp.mixins import ValidatePermissionRequiredMixin
from core.erp.models import Reference


# class ReferenceListView1(LoginRequiredMixin, ValidatePermissionRequiredMixin, ListView):
#     model = Reference
#     template_name = 'Reference/list.html'
#
#     @method_decorator(csrf_exempt)
#     @method_decorator(login_required)
#     def dispatch(self, request, *args, **kwargs):
#         return super().dispatch(request, *args, **kwargs)
#
#     def post(self, request, *args, **kwargs):
#         data = {}
#         try:
#             action = request.POST['action']
#             if action == 'searchdata':
#                 data = []
#                 departamento = request.user.department  # Supondo que o usuário esteja autenticado como chefe de departamento
#
#                 if departamento is not None:
#                     departamento = departamento
#                     todas_referencias = ""
#
#                     # 2. Em seguida, filtre os usuários que pertencem ao mesmo departamento, mas não são o próprio chefe:
#                     usuarios_departamento = User.objects.filter(department=departamento)
#
#                     # 3. Agora, obtenha todas as ausências (Absence) dos usuários do departamento, excluindo o chefe:
#                     referencias = Reference.objects.filter(user_department=departamento)
#
#                     # 4. Você pode iterar sobre "todas_ausencias" para processar os dados conforme necessário.
#
#                     # if departamento == "":
#                     #     todas_referencias = Reference.objects.filter(status='PENDENTE')
#
#                     for i in referencias:
#                         print(i, 'reference')
#                         data.append(i.toJson())
#             else:
#                 data['error'] = 'Ocorreu um erro na requisição'
#         except Exception as e:
#             print(e)
#             data['error'] = str(e)
#         return JsonResponse(data, safe=False)
#
#     def get_context_data(self, **kwargs):
#         # Call the base implementation first to get a context
#         context = super().get_context_data(**kwargs)
#         context["title"] = 'Lista de Referencias'
#         context["create_url"] = reverse_lazy('erp:absence_create')
#         context["list_url"] = reverse_lazy('erp:reference_list')
#         context["table"] = 'Reference'
#         # context["action"] = 'searchdata'
#         # context['departments'] = Department.objects.all()
#         return context


class ReferenceListView(LoginRequiredMixin, ValidatePermissionRequiredMixin, ListView):
    model = Reference
    template_name = 'reference/list.html'
    permission_required = 'erp.view_reference'

    @method_decorator(csrf_exempt)
    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        data = {}
        try:
            action = request.POST['action']
            if action == 'searchdata':
                data = []
                departamento = request.user.department  # Supondo que o usuário esteja autenticado como chefe de departamento

                if departamento is not None:
                    departamento = departamento

                    # 3. Agora, obtenha todas as ausências (Absence) dos usuários do departamento, excluindo o chefe:
                    referencias = Reference.objects.filter(user_department__exact=departamento)

                    # 4. Você pode iterar sobre "todas_ausencias" para processar os dados conforme necessário.
                    for i in referencias:
                        data.append(i.toJson())
            else:
                data['error'] = 'Ocorreu um erro na requisição'
        except Exception as e:
            print(e)
            data['error'] = str(e)
        return JsonResponse(data, safe=False)

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super().get_context_data(**kwargs)

        context["title"] = 'Lista de Referencias'
        context["create_url"] = reverse_lazy('erp:reference_create')
        context["list_url"] = reverse_lazy('erp:reference_list')
        context["table"] = 'Reference'
        context["action"] = 'searchdata'
        department = self.request.user.department
        context['contador'] = Reference.objects.filter(user_department__exact=department, date_created__month=datetime.now().month, date_created__year=datetime.now().year).count()
        return context


class ReferenceCreateView(LoginRequiredMixin, ValidatePermissionRequiredMixin, CreateView):
    model = Reference
    form_class = ReferenceForm
    template_name = 'reference/create.html'
    success_url = reverse_lazy('erp:reference_list')
    permission_required = 'erp.view_reference'

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        self.object = None
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        data = {}
        try:
            if request.POST['action'] == 'add':
                form = self.get_form()
                if form.is_valid():
                    data = form.save()
                    print(data)
                    #enviar_email_referencia(request.user, data['reference_code'])  # Envia o e-mail com o código de referência

                    data['success'] = 'Referência criada com sucesso!'
                else:
                    data['error'] = form.errors
            else:
                data['error'] = 'Não escolheu nenhuma opção válida'
        except Exception as e:
            data['error'] = str(e)
        return JsonResponse(data)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = 'Criar Referencias'
        context["entity"] = 'Referencias'
        context["table"] = 'Reference'
        context["action"] = 'add'
        context["list_url"] = reverse_lazy('erp:reference_list')
        context["create_url"] = reverse_lazy('erp:reference_create')
        context['user'] = self.request.user
        department = self.request.user.department
        context['contador'] = Reference.objects.filter(user_department__exact=department,
                                                       date_created__month=datetime.now().month,
                                                       date_created__year=datetime.now().year).count()
        return context


class ReferenceDeleteView(DeleteView):
    model = Reference
    template_name = 'reference/delete.html'
    success_url = reverse_lazy('erp:reference_list')
    permission_required = 'erp.delete_reference'

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()  # obtem o objeto que queremo eliminar
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        data = {}
        try:
            self.object.delete()  # eliminamos o objeto
        except Exception as e:
            data['error'] = str(e)
        return JsonResponse(data)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = 'Eliminar Referencia'
        context["entity"] = 'Referencia'
        context["table"] = 'Reference'
        # context["list_url"] = reverse_lazy('erp:Absence_list')
        context["list_url"] = reverse_lazy('erp:reference_list')
        context["remove_url"] = reverse_lazy('erp:reference_edit')
        return context


