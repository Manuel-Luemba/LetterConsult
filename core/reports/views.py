from django.http import JsonResponse
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import TemplateView
from core.erp.models import Letter
from core.reports.forms import ReportForm, LetterFilterForm


class ReportLetterView2(TemplateView):
    template_name = 'letter/report.html'

    @method_decorator(csrf_exempt)
    # @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        data = {}

        try:
            action = request.POST['action']
            if action == 'search_report':
                data = []
                start_date = request.POST.get('start_date', '')
                end_date = request.POST.get('end_date', '')
                search = Letter.objects.all().exclude(status__in= ['drafted'])
                if len(start_date) and len(end_date):
                    search = search.filter(date_sent__range=[start_date, end_date])
                for s in search:
                    data.append([
                        s.id,
                        s.reference_code.reference_code,
                        s.user_created.get_full_name(),
                        s.department.name,
                        s.date_sent.strftime('%Y-%m-%d'),
                        s.get_status_display()
                    ])
            else:
                data['error'] = 'Ocorreu um erro na requisição'
        except Exception as e:
            data['error'] = str(e)
        return JsonResponse(data, safe=False)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Reporte das Cartas'
        context['entity'] = 'Reportes'
        context['list_url'] = reverse_lazy('letter_report')
        context['form'] = ReportForm()
        return context


class ReportLetterView5(TemplateView):
    template_name = 'letter/report.html'

    @method_decorator(csrf_exempt)
    # @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        data = {}

        try:
            action = request.POST['action']
            if action == 'search_report':
                data = []
                start_date = request.POST.get('start_date', '')
                end_date = request.POST.get('end_date', '')
                search = Letter.objects.all().exclude(status='drafted')
                if len(start_date) and len(end_date):
                    search = search.filter(date_sent__range=[start_date, end_date])

                if len(start_date) and len(end_date):
                    search = search.filter(date_sent__range=[start_date, end_date])
                for s in search:

                    data.append(
                        s.toJson()
                        # s.reference_code.reference_code,
                        # s.user_created.get_full_name(),
                        # s.department.name,
                        # s.date_sent.strftime('%Y-%m-%d'),
                        # s.toJson() get_status_display()
                    )

            else:
                data['error'] = 'Ocorreu um erro na requisição'
        except Exception as e:
            data['error'] = str(e)
        return JsonResponse(data, safe=False)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Reporte das Cartas'
        context['entity'] = 'Reportes'
        context['list_url'] = reverse_lazy('letter_report')
        context['form'] = LetterFilterForm()
        return context


# class ReportLetterView(TemplateView):
#     template_name = 'letter/report.html'
#
#     @method_decorator(csrf_exempt)
#     def dispatch(self, request, *args, **kwargs):
#         return super().dispatch(request, *args, **kwargs)
#
#     def post(self, request, *args, **kwargs):
#         data = {}
#         try:
#             action = request.POST['action']
#             if action == 'search_report':
#                 data = []
#
#                 # Criar o filtro com base nos dados do formulário
#                 filterset = LetterFilter(request.POST, queryset=Letter.objects.all())
#
#                 if filterset.is_valid():
#                     # Obter as cartas filtradas
#                     search = filterset.qs
#
#                     # Montar os dados de resposta
#                     for s in search:
#                         data.append([
#                             s.id,
#                             s.reference_code.reference_code,
#                             s.user_created.get_full_name(),
#                             s.department.name,
#                             s.date_sent.strftime('%Y-%m-%d'),
#                             s.get_status_display()
#                         ])
#             else:
#                 data['error'] = 'Ocorreu um erro na requisição'
#         except Exception as e:
#             data['error'] = str(e)
#         return JsonResponse(data, safe=False)
#
#     def get_context_data(self, **kwargs):
#         context = super().get_context_data(**kwargs)
#         context['title'] = 'Reporte das Cartas'
#         context['entity'] = 'Reportes'
#         context['list_url'] = reverse_lazy('letter_report')
#
#         # Passando o formulário de filtro para o template
#         context['form'] = LetterFilter()
#         return context


class ReportLetterView(TemplateView):
    template_name = 'letter/report.html'

    @method_decorator(csrf_exempt)  # Exclui a verificação do CSRF
    # @method_decorator(login_required)  # Descomente para requerer autenticação
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        data = {}
        try:
            action = request.POST.get('action', '')
            if action == 'search_report':
                data = []
                start_date = request.POST.get('start_date', '')
                end_date = request.POST.get('end_date', '')
                department = request.POST.get('department', '')
                entity = request.POST.get('entity', '')
                status = request.POST.get('status', '')

                print(entity, 'MNO')

                # Filtra cartas excluindo as que estão em rascunho
                search = Letter.objects.exclude(status='drafted')

                # Aplica o filtro de intervalo de datas, se fornecido
                if start_date and end_date:
                    search = search.filter(date_sent__range=[start_date, end_date])
                if department:
                    search = search.filter(department=department)
                if entity:
                    search = search.filter(entity__contains=entity)
                if status:
                    search = search.filter(status=status)

                # Converte os resultados para JSON
                for s in search:
                    data.append(s.toJson())  # Certifique-se de que o método `toJson` esteja correto

            else:
                data['error'] = 'Ação não identificada ou inválida.'
        except Exception as e:
            data['error'] = str(e)

        return JsonResponse(data, safe=False)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Reporte das Cartas'
        context['entity'] = 'Reportes'
        context['list_url'] = reverse_lazy('letter_report')
        context['form'] = LetterFilterForm()  # Insere o formulário de filtros
        return context
