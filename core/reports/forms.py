from django.forms import *

from core.erp.models import Letter, Department


class ReportForm(Form):
    date_range = CharField(widget=TextInput(attrs={
        'class': 'form-control',
        'autocomplete': 'off',
        'id': 'protocol',
        'data-target': '#protocol',

    }))
    department = ModelChoiceField(queryset=Department.objects.all(), required=False,
                                  widget=Select(attrs=
                                  {
                                      'class': 'form-control',
                                      'id': 'protocol',
                                      'data-target': '#protocol',
                                  }))
    status = ChoiceField(choices=Letter.letter_status, required=False,
                         widget=Select(attrs=
                         {
                             'class': 'form-control',
                             'id': 'protocol',
                             'data-target': '#protocol',
                         }))


class LetterFilterForm(Form):
    start_date = DateField(required=False, label='Data inicial', widget=DateInput(
        attrs={
            'type': 'date',
            'class': 'form-control datetimepicker-input',
            'id': 'start_date',
            'data-target': '#start_date',
            'placeholder': 'YYYY-MM-DD'
        }))

    end_date = DateField(required=False, label='Data final', widget=DateInput(
        attrs={
            'type': 'date',
            'class': 'form-control datetimepicker-input',
            'id': 'end_date',
            'data-target': '#end_date',
            'placeholder': 'YYYY-MM-DD'
        }))
    department = ModelChoiceField(queryset=Department.objects.all(), required=False, label='Departamento',
                                  widget=Select(attrs=
                                  {
                                      'class': 'form-control',
                                      'id': 'department',
                                      'data-target': '#department',
                                  }))

    # Novo campo para filtrar pelo destinatário
    entity = CharField(required=False, label='Entidade', widget=TextInput(attrs={
        'class': 'form-control',
        'placeholder': 'Nome da entidade',
        'id': 'entity',
        'data-target': '#entity'
    }))
    status = ChoiceField(choices=Letter.letter_status, required=False, label='Estado',
                         widget=Select(attrs=
                         {
                             'class': 'form-control',
                             'id': 'status',
                             'data-target': '#status',
                         }))

    def __init__(self, *args, **kwargs):
        super(LetterFilterForm, self).__init__(*args, **kwargs)

        # Opções que você deseja remover
        options_to_remove = ['drafted', 'canceled']

        # Filtra as opções de status removendo as que estão na lista `options_to_remove`
        self.fields['status'].choices = [
            (key, value) for key, value in Letter.letter_status if key not in options_to_remove
        ]
