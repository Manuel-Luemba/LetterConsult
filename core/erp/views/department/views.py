from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.http import JsonResponse, HttpResponseRedirect
from django.urls import reverse_lazy
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, FormView
from django.utils.decorators import method_decorator

from core.erp.mixins import IsSuperuserMixin, ValidatePermissionRequiredMixin
from core.erp.models import *
from core.erp.forms import DepartamentForm


class DepartmentListView(LoginRequiredMixin, ValidatePermissionRequiredMixin, ListView):
    model = Department
    template_name = 'department/list.html'
    permission_required = 'erp.view_department'

    @method_decorator(csrf_exempt)
    # @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        data = {}

        try:
            action = request.POST['action']
            if action == 'searchdata':
                data = []
                for i in Department.objects.all():
                    data.append(i.toJson())
            else:
                data['error'] = 'Ocorreu um erro na requisição'
        except Exception as e:
            data['error'] = str(e)
        return JsonResponse(data, safe=False)

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super().get_context_data(**kwargs)
        context["title"] = 'Lista de Departamentos'
        context["create_url"] = reverse_lazy('erp:department_create')
        context["list_url"] = reverse_lazy('erp:department_list')
        context["entity"] = 'Departamento'
        # context["action"] = 'searchdata'
        # context['departments'] = Department.objects.all()
        return context


class DepartmentCreateView(LoginRequiredMixin,ValidatePermissionRequiredMixin,CreateView):
    model = Department
    form_class = DepartamentForm
    template_name = 'department/create.html'
    success_url = reverse_lazy('erp:department_list')
    permission_required = 'erp.add_department'
    url_redirect = success_url

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        self.object = None
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        data = {}
        try:
            if request.POST['action'] == 'add':
                form = self.get_form()
                data = form.save()
            else:
                data['error'] = 'Não escolheu nenhuma opção válida'
        except Exception as e:
            data['error'] = str(e)
        return JsonResponse(data)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = 'Criar Departamento'
        context["entity"] = 'Departamento'
        context["action"] = 'add'
        context["list_url"] = self.success_url
        context["create_url"] = reverse_lazy('erp:department_create')
        return context


class DepartmentUpdateView(LoginRequiredMixin,ValidatePermissionRequiredMixin,UpdateView):
    model = Department
    form_class = DepartamentForm
    template_name = 'department/create.html'
    success_url = reverse_lazy('erp:department_list')
    permission_required = 'erp.change_department'
    url_redirect = success_url


    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        data = {}
        try:
            if request.POST['action'] == 'edit':
                form = self.get_form()
                data = form.save()
            else:
                data['error'] = 'Não escolheu nenhuma opção válida'
        except Exception as e:
            data['error'] = str(e)
        return JsonResponse(data)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = 'Editar Departamento'
        context["entity"] = 'Departamentos'
        context["action"] = 'edit'
        context["list_url"] = self.success_url
        context["edit_url"] = reverse_lazy('erp:department_edit')
        return context


class DepartmentDeleteView(LoginRequiredMixin,ValidatePermissionRequiredMixin,DeleteView):
    model = Department
    template_name = 'department/delete.html'
    success_url = reverse_lazy('erp:department_list')
    permission_required = 'erp.delete_department'
    url_redirect = success_url

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
        context["title"] = 'Eliminar Departamento'
        context["entity"] = 'Departamento'
        context["list_url"] = self.success_url
        context["remove_url"] = reverse_lazy('erp:department_edit')
        return context


class DepartmentFormView(FormView):
    form_class = DepartamentForm
    template_name = 'department/create.html'
    success_url = reverse_lazy('erp:department_list')

    def form_valid(self, form):
        return super().form_valid(form)

    def form_invalid(self, form):
        print(form.errors)
        return super().form_invalid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = 'Form | Departamento'
        context["entity"] = 'Departamento'
        context["action"] = 'add'
        context["list_url"] = reverse_lazy('erp:department_list')
        context["create_url"] = reverse_lazy('erp:department_create')
        return context

