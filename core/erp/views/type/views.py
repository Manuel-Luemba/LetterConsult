from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.urls import reverse_lazy
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.utils.decorators import method_decorator

from core.erp.forms import TypeForm
from core.homepage.models import Type


class TypeListView(ListView):
    model = Type
    template_name = 'type/list.html'

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
                for i in Type.objects.all():
                    data.append(i.toJson())
            else:
                data['error'] = 'Ocorreu um erro na requisição'
        except Exception as e:
            data['error'] = str(e)
        return JsonResponse(data, safe=False)

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super().get_context_data(**kwargs)
        context["title"] = 'Lista de Motivos'
        context["create_url"] = reverse_lazy('erp:type_create')
        context["list_url"] = reverse_lazy('erp:type_list')
        context["entity"] = 'Motivo'
        # context["action"] = 'searchdata'
        # context['departments'] = Department.objects.all()
        return context


class TypeCreateView(CreateView):
    model = Type
    form_class = TypeForm
    template_name = 'type/create.html'
    success_url = reverse_lazy('erp:type_list')

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
        context["title"] = 'Criar Motivo'
        context["entity"] = 'Motivo'
        context["action"] = 'add'
        context["list_url"] = reverse_lazy('erp:type_list')
        context["create_url"] = reverse_lazy('erp:type_create')
        return context


class TypeUpdateView(UpdateView):
    model = Type
    form_class = TypeForm
    template_name = 'type/create.html'
    success_url = reverse_lazy('erp:type_list')

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
        context["title"] = 'Editar Motivo'
        context["entity"] = 'Motivo'
        context["action"] = 'edit'
        context["list_url"] = reverse_lazy('erp:type_list')
        context["edit_url"] = reverse_lazy('erp:type_edit')
        return context


class TypeDeleteView(DeleteView):
    model = Type
    template_name = 'type/delete.html'
    success_url = reverse_lazy('erp:type_list')

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
        context["title"] = 'Eliminar Motivo'
        context["entity"] = 'Motivo'
        context["list_url"] = reverse_lazy('erp:type_list')
        context["remove_url"] = reverse_lazy('erp:type_edit')
        return context
