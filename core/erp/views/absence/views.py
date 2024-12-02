import os
from io import BytesIO

from django.shortcuts import render
from weasyprint import HTML, CSS
from django.template.loader import get_template
from django.conf import settings
from django.http import HttpResponse

from django.contrib.staticfiles import finders

from crum import get_current_user
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin

from django.http import JsonResponse, HttpResponseRedirect

from django.urls import reverse_lazy
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, TemplateView
from django.utils.decorators import method_decorator

from core.erp.forms import AbsenceForm, AbsenceAdminForm
from core.erp.mixins import ValidatePermissionRequiredMixin

from core.homepage.models import Absence
from core.user.models import User


class AbsenceListView(LoginRequiredMixin, ValidatePermissionRequiredMixin, ListView):
    model = Absence
    template_name = 'Absence/list.html'
    permission_required = 'homepage.aprove_absence'

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
                chefe_departamento = request.user.department.manager  # Supondo que o usuário esteja autenticado como chefe de departamento

                if chefe_departamento.department is not None:
                    departamento = chefe_departamento.department
                    todas_ausencias = ""
                    if chefe_departamento == request.user:

                        # 2. Em seguida, filtre os usuários que pertencem ao mesmo departamento, mas não são o próprio chefe:
                        usuarios_departamento = User.objects.filter(department=departamento).exclude(
                            id=chefe_departamento.id)

                        # 3. Agora, obtenha todas as ausências (Absence) dos usuários do departamento, excluindo o chefe:
                        todas_ausencias = Absence.objects.filter(user_created__in=usuarios_departamento)

                        # 4. Você pode iterar sobre "todas_ausencias" para processar os dados conforme necessário.

                        if departamento == "":
                            todas_ausencias = Absence.objects.filter(status='PENDENTE')

                        for i in todas_ausencias:
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
        context["title"] = 'Lista de Ausências'
        context["create_url"] = reverse_lazy('erp:Absence_create')
        context["list_url"] = reverse_lazy('erp:absence_list')
        context["table"] = 'Absence'
        # context["action"] = 'searchdata'
        # context['departments'] = Department.objects.all()
        return context


class MyAbsenceListView(LoginRequiredMixin, ValidatePermissionRequiredMixin, ListView):
    model = Absence
    template_name = 'Absence/my.html'
    permission_required = 'homepage.view_absence'

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
                user = get_current_user()
                for i in Absence.objects.filter(user_created=user):
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
        context["title"] = 'Lista de Ausências'
        context["entity"] = 'Ausência'
        context["table"] = 'Absence'
        context["manager"] = 'NÃO'
        context['user'] = self.request.user
        # context["create_url"] = reverse_lazy('erp:Absence_create')
        # context["create_url"] = reverse_lazy('erp:Absence_create')
        context["list_url"] = reverse_lazy('erp:absence_my_list')


        # Verifique se o usuário é chefe de departamento (você precisará adaptar isso à sua lógica real)
        user_is_department_head = self.request.user.department.manager  # Exemplo hipotético

        if user_is_department_head == self.request.user:
            context["create_url"] = reverse_lazy('erp:absence_create_aprove')
            context["manager"] = 'SIM'
        else:
            context["create_url"] = reverse_lazy('erp:absence_create')
            context["manager"] = 'NÃO'
        return context


class AbsenceCreateView(LoginRequiredMixin, ValidatePermissionRequiredMixin, CreateView):
    model = Absence
    form_class = AbsenceForm
    template_name = 'Absence/create.html'
    success_url = reverse_lazy('erp:absence_list')
    #permission_required = 'homepage.aprove_absence'
    permission_required = 'homepage.view_absence'

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
        context["title"] = 'Criar Ausências'
        context["entity"] = 'Ausências'
        context["table"] = 'Absence'
        context["action"] = 'add'
        context["list_url"] = reverse_lazy('erp:absence_my_list')
        context["create_url"] = reverse_lazy('erp:absence_create')
        return context


class AbsenceUpdateView(LoginRequiredMixin, ValidatePermissionRequiredMixin, UpdateView):
    model = Absence
    form_class = AbsenceForm
    template_name = 'Absence/create.html'
    success_url = reverse_lazy('erp:absence_list')
    #permission_required = 'homepage.aprove_absence'
    permission_required = 'homepage.view_absence'

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
        context["title"] = 'Editar Ausência'
        context["entity"] = 'Ausência'
        context["table"] = 'Absence'
        context["action"] = 'edit'
        context["list_url"] = reverse_lazy('erp:absence_my_list')
        context["edit_url"] = reverse_lazy('erp:absence_edit')
        return context


class AbsenceDeleteView(DeleteView):
    model = Absence
    template_name = 'Absence/delete.html'
    success_url = reverse_lazy('erp:absence_list')
    permission_required = 'homepage.delete_absence'

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
        context["title"] = 'Eliminar Ausência'
        context["entity"] = 'Ausência'
        context["table"] = 'Absence'
        # context["list_url"] = reverse_lazy('erp:Absence_list')
        context["list_url"] = reverse_lazy('erp:absence_my_list')
        context["remove_url"] = reverse_lazy('erp:absence_edit')
        return context


class AproveUpdateAbsenceView(UpdateView):
    model = Absence
    form_class = AbsenceAdminForm
    template_name = 'Absence/create.html'
    success_url = reverse_lazy('erp:absence_list')
    # success_url = reverse_lazy('erp:Absence_my_list')
    permission_required = 'homepage.aprove_absence'

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
        context["title"] = 'Editar Ausência'
        context["entity"] = 'Ausência'
        context["table"] = 'Absence'
        context["action"] = 'edit'
        context["manager"] = 'NÃO'
        # if context['manager'] == "NÃO":
        #     context["list_url"] = reverse_lazy('erp:Absence_list')
        # else:
        #     context["list_url"] = reverse_lazy('erp:Absence_my_list')
        # context["edit_url"] = reverse_lazy('erp:Absence_edit')
        # print(context['manager'])
        # return context

        # Verifique se o usuário é chefe de departamento (você precisará adaptar isso à sua lógica real)
        user_is_department_head = self.request.user.department.manager  # Exemplo hipotético
        print(self.request)

        if user_is_department_head == self.request.user:
            context["create_url"] = reverse_lazy('erp:absence_create_aprove')
            context["list_url"] = reverse_lazy('erp:absence_list')
            context["manager"] = 'SIM'
        else:
            context["create_url"] = reverse_lazy('erp:absence_create')
            context["manager"] = 'NÃO'

        print(context["manager"])
        return context


class AproveUpdateManagerAbsenceView(UpdateView):
    model = Absence
    form_class = AbsenceAdminForm
    template_name = 'Absence/create.html'
    #success_url = reverse_lazy('erp:absence_list')
    success_url = reverse_lazy('erp:Absence_my_list')
    permission_required = 'homepage.aprove_absence'

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
        context["title"] = 'Editar Ausência'
        context["entity"] = 'Ausência'
        context["table"] = 'Absence'
        context["action"] = 'edit'
        context["manager"] = 'NÃO'
        # if context['manager'] == "NÃO":
        #     context["list_url"] = reverse_lazy('erp:Absence_list')
        # else:
        #     context["list_url"] = reverse_lazy('erp:Absence_my_list')
        # context["edit_url"] = reverse_lazy('erp:Absence_edit')
        # print(context['manager'])
        # return context

        # Verifique se o usuário é chefe de departamento (você precisará adaptar isso à sua lógica real)
        user_is_department_head = self.request.user.department.manager  # Exemplo hipotético

        if user_is_department_head == self.request.user:
            context["create_url"] = reverse_lazy('erp:absence_create_aprove')
            context["list_url"] = reverse_lazy('erp:absence_my_list')
            context["manager"] = 'SIM'
        else:
            context["create_url"] = reverse_lazy('erp:absence_create')
            context["manager"] = 'NÃO'
        return context


class AproveCreateAbsenceView(LoginRequiredMixin, ValidatePermissionRequiredMixin, CreateView):
    model = Absence
    form_class = AbsenceAdminForm
    template_name = 'Absence/create.html'
    success_url = reverse_lazy('erp:absence_my_list')
    permission_required = 'homepage.aprove_absence'

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
        context["title"] = 'Criar Ausências'
        context["entity"] = 'Ausência'
        context["table"] = 'Absence'
        context["action"] = 'add'
        # context["list_url"] = reverse_lazy('erp:Absence_list')
        # context["create_url"] = reverse_lazy('erp:Absence_create')

        # Verifique se o usuário é chefe de departamento (você precisará adaptar isso à sua lógica real)
        user_is_department_head = self.request.user.department.manager  # Exemplo hipotético

        if user_is_department_head == self.request.user:
            context["create_url"] = reverse_lazy('erp:absence_create_aprove')
            context["list_url"] = reverse_lazy('erp:absence_my_list')
        else:
            context["create_url"] = reverse_lazy('erp:absence_create')
            context["list_url"] = reverse_lazy('erp:absence_list')
        return context


class AbsenceInfoPdf(View):

    # def link_callback(uri, rel):
    #     """
    #     Convert HTML URIs to absolute system paths so xhtml2pdf can access those
    #     resources
    #     """
    #     result = finders.find(uri)
    #     if result:
    #         if not isinstance(result, (list, tuple)):
    #             result = [result]
    #         result = list(os.path.realpath(path) for path in result)
    #         path = result[0]
    #     else:
    #         sUrl = settings.STATIC_URL  # Typically /static/
    #         sRoot = settings.STATIC_ROOT  # Typically /home/userX/project_static/
    #         mUrl = settings.MEDIA_URL  # Typically /media/
    #         mRoot = settings.MEDIA_ROOT  # Typically /home/userX/project_static/media/
    #
    #         if uri.startswith(mUrl):
    #             path = os.path.join(mRoot, uri.replace(mUrl, ""))
    #         elif uri.startswith(sUrl):
    #             path = os.path.join(sRoot, uri.replace(sUrl, ""))
    #         else:
    #             return uri
    #
    #     # make sure that file exists
    #     if not os.path.isfile(path):
    #         raise RuntimeError(
    #             'media URI must start with %s or %s' % (sUrl, mUrl)
    #         )
    #     return path

    def get(self, request, *args, **kwargs):
        try:
            template = get_template('Absence/invoice.html')
            context = {
                'absence': Absence.objects.get(pk=self.kwargs['pk']),
                'emp': {'name': 'ENGCONSULT', 'nif': 5417126500, 'contactos': '934474744',
                        'address': 'RUA KATYAVALA, EDIF. AVENCA PLAZA 7º PISO', 'director':'Cláudio Francisco'},
                'icon': '{}{}'.format(settings.MEDIA_URL, '/logo.png')
            }

            html = template.render(context)
            css_url = os.path.join(settings.BASE_DIR, 'static/lib/bootstrap-4.4.1-dist/css/bootstrap.min.css')
            pdf = HTML(string=html, base_url=request.build_absolute_uri()).write_pdf(stylesheets=[CSS(css_url)])


            return HttpResponse(pdf, content_type='application/pdf')

            # response['Content-Disposition'] = 'attachment; filename="report.pdf"'

            # # create a pdf
            # pisa_status = pisa.CreatePDF(
            #     html, dest=response)

            # if error then show some funny view
            # if pisa_status.err:
            #     return HttpResponse('We had some errors <pre>' + html + '</pre>')
            # return response
        except:
            pass
        return HttpResponseRedirect(reverse_lazy('erp:absence_my_list'))

from django.http import HttpResponse
from django.views.generic import View
from django.template.loader import get_template
from xhtml2pdf import pisa

class AbsenceViewPdf(TemplateView):

        template_name = 'Absence/invoice.html'  # Nome do seu template HTML

        def get_context_data(self, **kwargs):
            context = super().get_context_data(**kwargs)
            context = {
                'absence': Absence.objects.get(pk=self.kwargs['pk']),
                'reason': Absence.objects.get(pk=self.kwargs['pk']),
                'emp': {'name': 'ENGCONSULT', 'nif': 5417126500, 'contactos': '934474744',
                        'address': 'RUA KATYAVALA, EDIF. AVENCA PLAZA 7º PISO', 'director': 'Cláudio Francisco'},
                'icon': '{}{}'.format(settings.MEDIA_URL, '/logo.png')
            }

            return context

class GeneratePdf(View):
    def get(self, request, *args, **kwargs):
        # Defina o contexto para o seu template (se necessário)
        context = {'myvar': 'este é o contexto do seu template'}

        # Renderize o template HTML
        template = get_template('Absence/invoice.html')
        html = template.render(context)
        # Crie um PDF a partir do HTML
        pdf = self.html_to_pdf(html)
        if pdf:
            response = HttpResponse(pdf, content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="report.pdf"'
            return response
        else:
            return HttpResponse('Ocorreu um erro ao gerar o PDF.')

    def html_to_pdf(self, html):
        result = BytesIO()
        pdf = pisa.pisaDocument(BytesIO(html.encode("ISO-8859-1")), result)
        if not pdf.err:
            return result.getvalue()
        return None