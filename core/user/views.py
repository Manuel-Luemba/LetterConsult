from email.headerregistry import Group

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib.auth.models import Group
from django.http import JsonResponse, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse_lazy
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, FormView
from django.utils.decorators import method_decorator

from core.erp.mixins import IsSuperuserMixin, ValidatePermissionRequiredMixin
from core.erp.models import *
from core.user.forms import UserForm
from core.user.models import User


class UserListView(LoginRequiredMixin, ValidatePermissionRequiredMixin, ListView):
    model = User
    template_name = 'user/list.html'
    permission_required = 'user.view_user'

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
                for i in User.objects.all():
                    data.append(i.toJSON())

            else:
                data['error'] = 'Ocorreu um erro na requisição'
        except Exception as e:
            data['error'] = str(e)
        return JsonResponse(data, safe=False)

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super().get_context_data(**kwargs)
        context["title"] = 'Lista de Usuários'
        context["create_url"] = reverse_lazy('user:user_create')
        context["list_url"] = reverse_lazy('user:user_list')
        context["entity"] = 'Usuários'
        context["model"] = 'Usuário'
        # context["action"] = 'searchdata'
        # context['users'] = Employee.objects.all()
        return context


class UserCreateView(LoginRequiredMixin, ValidatePermissionRequiredMixin, CreateView):
    model = User
    form_class = UserForm
    template_name = 'user/create.html'
    success_url = reverse_lazy('user:user_list')
    permission_required = 'user.add_user'
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
        context["title"] = 'Criar Usuário'
        context["entity"] = 'Usuários'
        context["model"] = 'Usuário'
        context["action"] = 'add'
        context["list_url"] = self.success_url
        context["create_url"] = reverse_lazy('user:user_create')
        return context


class UserUpdateView(LoginRequiredMixin, ValidatePermissionRequiredMixin, UpdateView):
    model = User
    form_class = UserForm
    template_name = 'user/create.html'
    success_url = reverse_lazy('user:user_list')
    permission_required = 'user.change_user'
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
        context["title"] = 'Editar Usuário'
        context["entity"] = 'Usuários'
        context["model"] = 'Usuário'
        context["action"] = 'edit'
        context["list_url"] = self.success_url
        context["edit_url"] = reverse_lazy('user:user_edit')
        return context


class UserDeleteView(LoginRequiredMixin, ValidatePermissionRequiredMixin, DeleteView):
    model = User
    template_name = 'user/delete.html'
    success_url = reverse_lazy('user:user_list')
    permission_required = 'user.delete_user'
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
        context["title"] = 'Eliminar Usuário'
        context["entity"] = 'Usuário'
        context["list_url"] = self.success_url
        context["remove_url"] = reverse_lazy('user:user_edit')
        return context


class UserChangeGroup(LoginRequiredMixin, View):

    def get(self, request, *args, **kwargs):
        try:
            request.session['group'] = Group.objects.get(pk= self.kwargs['pk'])
        except:
            pass
        return HttpResponseRedirect(reverse_lazy('erp:dashboard'))
