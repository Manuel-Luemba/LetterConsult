from datetime import datetime

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Min, Max,Q
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import TemplateView

from core.erp.models import Letter


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'dashboard.html'

    @method_decorator(csrf_exempt)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        request.user.get_group_session()
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        data = {}
        try:
            action = request.POST['action']
            if action == 'graph_letter_department_year':
                data = {
                    'name': 'Total de Cartas',
                    'showInLegend': False,
                    'colorByPoint': True,
                    'data': self.get_graph_letter_department_year()
                }

            elif action == 'get_status_data':
                data = {
                    'name': 'Cartas por Status',
                    'showInLegend': False,
                    'colorByPoint': True,
                    'data': self.get_status_data()
                }
            elif action == 'get_dashboard_entity_data':
                data = {
                    'name': 'Cartas por entidade',
                    'colorByPoint': True,
                    'data': self.get_dashboard_entity_data(),
                }

            elif action == 'get_letters_by_department_status':
                data = {
                    'name': 'Cartas Status por Departamento',
                    'colorByPoint': True,
                    'data': self.get_letters_by_department_status(),
                }
            else:
                data['error'] = 'Ha ocurrido un error'
        except Exception as e:
            data['error'] = str(e)
        return JsonResponse(data, safe=False)

    def get_graph_letter_department_year(self):
        data = {}
        year = datetime.now().year
        # Agrupar cartas por departamento e ano
        letters_by_department = (
            Letter.objects.filter(date_sent__year=year)
            .exclude(status__in='drafted')  # Exclui cartas com status 'drafted'
            .values('department__name')
            .annotate(total=Count('id'))
            .order_by('department__name')
        )


        # Obter o ano mais antigo e mais recente de cartas enviadas
        year_range = Letter.objects.aggregate(min_year=Min('date_sent__year'), max_year=Max('date_sent__year'))
        years = list(range(year_range['min_year'], year_range['max_year'] + 1))  # Gera a lista de anos

        # Agrupar cartas por departamento e ano para cada ano no intervalo
        chart_data = []
        for year in years:
            letters_by_department = (
                Letter.objects.filter(date_sent__year=year)  # Filtra por ano
                .values('department__name')  # Acessa o nome do departamento
                .exclude(status='drafted')
                .annotate(total=Count('id'))  # Conta o número de cartas por departamento
                .order_by('department__name')  # Ordena pelo nome do departamento
            )

            # Preparar dados para o gráfico
            departments_totals = [entry['total'] for entry in
                                  letters_by_department]  # Lista de totais por departamento
            department_names = ""
            # Adicionar nomes dos departamentos na lista se ainda não estiverem nela
            if not department_names:
                department_names = [entry['department__name'] for entry in
                                    letters_by_department]  # Nome dos departamentos

            # Adicionar série de dados no formato do Highcharts
            chart_data.append({
                'type': 'column',
                'name': str(year),  # Nome da série será o ano
                'data': departments_totals  # Totais das cartas por departamento no ano
            })

        return {
            'departments': department_names,
            'years': chart_data  # Totais das cartas por departamento no ano

        }

    def get_status_data(self):
        # Dicionário para mapear status para seus rótulos em português
        status_map = dict(Letter.letter_status)  # {'drafted': 'Rascunho', 'submitted': 'Submetida', ...}
        # Agrupar cartas por status
        letters_by_status = (
            Letter.objects
            .values('status')
            .exclude(status='drafted')  # Exclui cartas em rascunho
            .annotate(total=Count('id'))  # Conta o número de cartas por status
            .order_by('status')  # Ordena pelo status
        )

        # Preparar dados para o gráfico
        statuses = [status_map[entry['status']] for entry in letters_by_status]  # Usa o status em português
        totals = [entry['total'] for entry in letters_by_status]

        return {
            'statuses': statuses,  # Retorna os status
            'totals': totals  # Retorna o total de cartas por status
        }

    def get_dashboard_entity_data(self):
        # Agrupar cartas por função (job) e entidade (entity)

        letters_by_entity = (
            Letter.objects.values('entity')
            .exclude(status='drafted')  # Excluir cartas no estado de rascunho, se necessário
            .annotate(total=Count('id'))
            .order_by('entity')
        )

        # Preparar dados para o gráfico
        entities = [entry['entity'] for entry in letters_by_entity]  # Lista de entidades
        entity_totals = [entry['total'] for entry in letters_by_entity]  # Total de cartas por entidade

        return {
            'entities': entities,
            'entity_totals': entity_totals
        }

    def get_letters_by_department_status(self):
        # Filtrar cartas excluindo o status 'drafted'
        letters = Letter.objects.filter(~Q(status='drafted'))

        # Agrupar por departamento e status
        data = letters.values('department__name', 'status').annotate(total=Count('id')).order_by('department__name',
                                                                                                 'status')
        departments = set()
        statuses = ['sent', 'approved', 'submitted', 'rejected']  # Status que queremos acompanhar
        department_status_data = {status: {} for status in statuses}
        print(department_status_data, 'department_status_data')
        # Organizar os dados
        for entry in data:
            department = entry['department__name']
            status = entry['status']
            total = entry['total']
            departments.add(department)
            department_status_data[status][department] = total

        #Garantir que cada departamento tenha todos os status (mesmo que zero)
        final_data = {status: [department_status_data[status].get(department, 0) for department in departments] for
                      status in statuses}

        # Montar a resposta com os dados
        return {
            'departments': list(departments),
            'series': [
                {'name': 'Enviada', 'data': final_data['sent']},
                {'name': 'Cancelada', 'data': final_data['rejected']},
                {'name': 'Aprovada', 'data': final_data['approved']},

                {'name': 'Submetida', 'data': final_data['submitted']}
            ]
        }


    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['panel'] = 'Painel de administrador'
        context['action'] = 'graph_letter_department_year'
        context['graph_letter_department_year'] = self.get_graph_letter_department_year()
        context['month'] = datetime.now().month
        context['approved_number'] = Letter.objects.filter(status='approved').count()
        context['sent_number'] = Letter.objects.filter(status='sent').count()
        context['submitted_number'] = Letter.objects.filter(status='submitted').count()
        context['rejected_number'] = Letter.objects.filter(status='rejected').count()
        current_year = datetime.now().year
        years = range(2015, current_year + 1)
        context['range'] = years  # Lista de anos para o dropdown
        return context
