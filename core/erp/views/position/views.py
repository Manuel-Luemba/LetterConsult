from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.urls import reverse_lazy
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.utils.decorators import method_decorator

from core.erp.forms import PositionForm
from core.homepage.models import Position


class PositionListView(ListView):
    model = Position
    template_name = 'position/list.html'

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
                for i in Position.objects.all():
                    data.append(i.toJson())
            else:
                data['error'] = 'Ocorreu um erro na requisição'
        except Exception as e:
            data['error'] = str(e)
        return JsonResponse(data, safe=False)

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super().get_context_data(**kwargs)
        context["title"] = 'Lista de Cargos'
        context["create_url"] = reverse_lazy('erp:position_create')
        context["list_url"] = reverse_lazy('erp:position_list')
        context["entity"] = 'Cargo'
        # context["action"] = 'searchdata'
        # context['departments'] = Department.objects.all()
        return context


class PositionCreateView(CreateView):
    model = Position
    form_class = PositionForm
    template_name = 'position/create.html'
    success_url = reverse_lazy('erp:position_list')

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
        context["title"] = 'Criar Cargo'
        context["entity"] = 'Cargo'
        context["action"] = 'add'
        context["list_url"] = reverse_lazy('erp:position_list')
        context["create_url"] = reverse_lazy('erp:position_create')
        return context


class PositionUpdateView(UpdateView):
    model = Position
    form_class = PositionForm
    template_name = 'position/create.html'
    success_url = reverse_lazy('erp:position_list')

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
        context["title"] = 'Editar Cargo'
        context["entity"] = 'Cargo'
        context["action"] = 'edit'
        context["list_url"] = reverse_lazy('erp:position_list')
        context["edit_url"] = reverse_lazy('erp:position_edit')
        return context


class PositionDeleteView(DeleteView):
    model = Position
    template_name = 'position/delete.html'
    success_url = reverse_lazy('erp:position_list')

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
        context["title"] = 'Eliminar Cargo'
        context["entity"] = 'Cargo'
        context["list_url"] = reverse_lazy('erp:position_list')
        context["remove_url"] = reverse_lazy('erp:position_edit')
        return context
