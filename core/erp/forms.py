from ckeditor.fields import RichTextField
from ckeditor.widgets import CKEditorWidget
from crum import get_current_user
from django.forms import *
from django_ckeditor_5.widgets import CKEditor5Widget

from core.erp.models import Department, Reference, Letter
from core.homepage.models import Type, Absence, Position
from core.user.models import User


class DepartamentForm(ModelForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # for form in self.visible_fields():
        #      form.field.widget.attrs['class'] = 'form-control'
        #      form.field.widget.attrs['autocomplete'] = 'off'
        self.fields['name'].widget.attrs['autofocus'] = True

    class Meta:
        model = Department
        fields = "__all__"
        widgets = {
            'name': TextInput(
                attrs={
                    'placeholder': 'Insira o nome do departamento'
                }
            ),

            'manager': Select(
                attrs={
                    'class': 'select2',
                    'style': 'width: 100%',
                    'id': 'manager',
                    'data-target': '#manager'
                }
            ),
            'desc': Textarea(
                attrs={
                    'placeholder': 'Insira a descrição do departamento (Opcional)',
                    'rows': 3,
                    'cols': 4
                }
            )
        }

    def save(self, commit=True):
        data = {}
        form = super()
        try:
            if form.is_valid():
                form.save()
            else:
                data['error'] = form.errors
        except Exception as e:
            data['error'] = str(e)
        return data


class PositionForm(ModelForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # for form in self.visible_fields():
        #      form.field.widget.attrs['class'] = 'form-control'
        #      form.field.widget.attrs['autocomplete'] = 'off'
        self.fields['name'].widget.attrs['autofocus'] = True

    class Meta:
        model = Position
        fields = "__all__"
        widgets = {
            'name': TextInput(
                attrs={
                    'placeholder': 'Insira o nome da Cargo'
                }
            ),
            'desc': Textarea(
                attrs={
                    'placeholder': 'Insira a descrição do Cargo (Opcional)',
                    'rows': 3,
                    'cols': 4
                }
            )
        }

    def save(self, commit=True):
        data = {}
        form = super()
        try:
            if form.is_valid():
                form.save()
            else:
                data['error'] = form.errors
        except Exception as e:
            data['error'] = str(e)
        return data


class TypeForm(ModelForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # for form in self.visible_fields():
        #      form.field.widget.attrs['class'] = 'form-control'
        #      form.field.widget.attrs['autocomplete'] = 'off'
        self.fields['name'].widget.attrs['autofocus'] = True

    class Meta:
        model = Type
        fields = "__all__"
        widgets = {
            'name': TextInput(
                attrs={
                    'placeholder': 'Insira o Motivo'
                }
            ),
            'desc': Textarea(
                attrs={
                    'placeholder': 'Insira a descrição (Opcional)',
                    'rows': 3,
                    'cols': 4
                }
            )
        }

    def save(self, commit=True):
        data = {}
        form = super()
        try:
            if form.is_valid():

                form.save()
            else:
                data['error'] = form.errors
        except Exception as e:
            data['error'] = str(e)
        return data


class AbsenceForm(ModelForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for form in self.visible_fields():
            form.field.widget.attrs['class'] = 'form-control'
            form.field.widget.attrs['autocomplete'] = 'off'

        self.fields['type'].widget.attrs['autofocus'] = True
        self.fields['type'].widget.attrs['class'] = 'select2'
        self.fields['type'].widget.attrs['id'] = 'type'
        self.fields['type'].widget.attrs['style'] = 'width: 100%'
        self.fields['type'].queryset = Type.objects.all()

        self.fields['start_date'].widget.attrs = {
            'class': 'form-control datetimepicker-input',
            'autocomplete': 'off',
            'id': 'start_date',
            'data-target': '#start_date',
            'data-toggle': 'datetimepicker'
        }

        self.fields['end_date'].widget.attrs = {
            'class': 'form-control datetimepicker-input',
            'autocomplete': 'off',
            'id': 'end_date',
            'data-target': '#end_date',
            'data-toggle': 'datetimepicker'
        }

    class Meta:
        model = Absence
        fields = "__all__"
        exclude = ["status", "user_created", "user_updated", "days_absence"]

        widgets = {

            # 'type': Select(
            #     attrs={
            #         'class': 'form-control select2',
            #         'style': 'width: 100%',
            #         'id': 'type',
            #         'data-target': '#type',
            #
            #     }
            # ),

            'start_date': DateInput(
                format='%Y-%m-%d',
                attrs={
                    'class': 'form-control datetimepicker-input',
                    'autocomplete': 'off',
                    'id': 'start_date',
                    'data-target': '#start_date',
                    'data-toggle': 'datetimepicker'

                }),

            'end_date': DateInput(
                format='%Y-%m-%d',
                attrs={
                    'class': 'form-control datetimepicker-input',
                    'autocomplete': 'off',
                    'id': 'end_date',
                    'data-target': '#end_date',
                    'data-toggle': 'datetimepicker'

                })
        }

    def save(self, commit=True):
        data = {}
        form = super()
        try:
            if form.is_valid():
                form.save()
            else:
                data['error'] = form.errors
        except Exception as e:
            data['error'] = str(e)
        return data


class AbsenceAdminForm(ModelForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # for form in self.visible_fields():
        #      form.field.widget.attrs['class'] = 'form-control'
        #      form.field.widget.attrs['autocomplete'] = 'off'
        self.fields['type'].widget.attrs['autofocus'] = True
        self.fields['type'].widget.attrs['class'] = 'select2'
        self.fields['type'].widget.attrs['id'] = 'type'
        self.fields['type'].widget.attrs['style'] = 'width: 100%'
        self.fields['type'].queryset = Type.objects.all()

        self.fields['start_date'].widget.attrs = {
            'class': 'form-control datetimepicker-input',
            'autocomplete': 'off',
            'id': 'start_date',
            'data-target': '#start_date',
            'data-toggle': 'datetimepicker'

        }

        self.fields['end_date'].widget.attrs = {
            'class': 'form-control datetimepicker-input',
            'autocomplete': 'off',
            'id': 'end_date',
            'data-target': '#end_date',
            'data-toggle': 'datetimepicker'

        }

    class Meta:
        model = Absence
        fields = "__all__"
        exclude = ["user_created", "user_updated", "days_absence"]

        # widgets = {
        #     'name': TextInput(
        #         attrs={
        #             'placeholder': 'Insira o Motivo'
        #         }
        #     ),
        #     'desc': Textarea(
        #         attrs={
        #             'placeholder': 'Insira a descrição (Opcional)',
        #             'rows': 3,
        #             'cols': 4
        #         }
        #     )
        # }

    def save(self, commit=True):
        data = {}
        form = super()
        try:
            if form.is_valid():
                form.save()
            else:
                data['error'] = form.errors
        except Exception as e:
            data['error'] = str(e)
        return data


class ReferenceForm(ModelForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for form in self.visible_fields():
             form.field.widget.attrs['class'] = 'form-control'
             form.field.widget.attrs['autocomplete'] = 'off'
        for field in self.fields:
            self.fields[field].widget.attrs['readonly'] = True

    class Meta:
        model = Reference
        fields = "__all__"
        exclude = ['user_created', 'user_updated']
        widgets = {
            # 'name': TextInput(
            #     attrs={
            #         'placeholder': 'Insira o nome do departamento'
            #     }
            # ),

            'user_created': Select(
                attrs={
                    'class': 'select2',
                    'style': 'width: 100%',
                    'id': 'user_created',
                    'data-target': '#user_created'
                }
            ),
            # 'desc': Textarea(
            #     attrs={
            #         'placeholder': 'Insira a descrição do departamento (Opcional)',
            #         'rows': 3,
            #         'cols': 4
            #     }
            # )
        }

    def save(self, commit=True):
        data = {}
        form = super()
        try:
            if form.is_valid():
               data = form.save().toJson()
            else:
                data['error'] = form.errors
        except Exception as e:
            data['error'] = str(e)
        return data


# class LetterForm1(ModelForm):
#
#     def __init__(self, *args, **kwargs):
#         super().__init__(*args, **kwargs)
#         for form in self.visible_fields():
#             form.field.widget.attrs['class'] = 'form-control'
#             form.field.widget.attrs['autocomplete'] = 'off'
#         self.fields['reason'].widget.attrs['autofocus'] = True
#
#         self.fields['body'].widget.attrs = {
#             'class': 'form-control',
#             'autocomplete': 'off',
#             'id': 'body',
#             'data-target': '#body',
#             'placeholder': 'Escreva o corpo da carta'
#         }
#
#         self.fields['reference_code'].widget.attrs = {
#             'class': 'form-control',
#             'autocomplete': 'off',
#             'id': 'reference_code',
#             'data-target': '#reference_code',
#             'readOnly': True,
#             'placeholder': 'Escreva o corpo da carta'
#         }
#
#         self.fields['user'].widget.attrs = {
#             'class': 'form-control',
#             'autocomplete': 'off',
#             'id': 'user',
#             'data-target': '#user',
#             'readOnly': True,
#             'placeholder': 'Escreva o corpo da carta'
#         }
#
#         # self.fields['date_sent'].widget.attrs = {
#         #     'class': 'form-control datetimepicker-input',
#         #     'autocomplete': 'off',
#         #     'id': 'date_sent',
#         #     'data-target': '#date_sent',
#         #     'data-toggle': 'datetimepicker'
#         #
#         # }
#
#     class Meta:
#         model = Letter
#         fields = "__all__"
#         exclude = ['status', 'user_created', 'user_updated']
#         widgets = {
#             'reason': TextInput(
#                 attrs={
#                     'placeholder': 'Escreva o assunto da carta'
#                 }
#             ),
#
#             'reference_code': Select(
#
#             ),
#
#             'user': TextInput(
#
#             ),
#             'date_sent': DateInput(
#                 format='%Y-%m-%d',
#                 attrs={
#                     'class': 'form-control datetimepicker-input',
#                     'autocomplete': 'off',
#                     'id': 'date_sent',
#                     'data-target': '#date_sent',
#                     'data-toggle': 'datetimepicker'
#
#                 }),
#
#             'body': Textarea(
#                 attrs={
#                     'placeholder': 'Insira a descrição do departamento (Opcional)',
#                     'rows': 10,
#                     'cols': 40
#                 }
#             )
#         }
#
#     def save(self, commit=True):
#         data = {}
#         form = super()
#         try:
#             if form.is_valid():
#                 form.save()
#             else:
#                 data['error'] = form.errors
#         except Exception as e:
#             data['error'] = str(e)
#         return data


class LetterAdminForm(ModelForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # for form in self.visible_fields():
        #      form.field.widget.attrs['class'] = 'form-control'
        #      form.field.widget.attrs['autocomplete'] = 'off'
        # self.fields['name'].widget.attrs['autofocus'] = True

    class Meta:
        model = Letter
        fields = "__all__"
        exclude = ['status', 'user_created', 'user_updated']
        widgets = {
            # 'name': TextInput(
            #     attrs={
            #         'placeholder': 'Insira o nome do departamento'
            #     }
            # ),

            'user_created': Select(
                attrs={
                    'class': 'select2',
                    'style': 'width: 100%',
                    'id': 'user_created',
                    'data-target': '#user_created'
                }
            ),
            # 'desc': Textarea(
            #     attrs={
            #         'placeholder': 'Insira a descrição do departamento (Opcional)',
            #         'rows': 3,
            #         'cols': 4
            #     }
            # )
        }

    def save(self, commit=True):
        data = {}
        form = super()
        try:
            if form.is_valid():
                form.save()
            else:
                data['error'] = form.errors
        except Exception as e:
            data['error'] = str(e)
        return data


class LetterForm(ModelForm):
    content = RichTextField(config_name='awesome_ckeditor')


    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', get_current_user())

        super(LetterForm, self).__init__(*args, **kwargs)
        for form in self.visible_fields():
            form.field.widget.attrs['class'] = 'form-control'
            form.field.widget.attrs['autocomplete'] = 'off'

        if self.instance and self.instance.status == 'approved':
            for field in self.fields:
                pass
                # if field not in ['status', 'protocol']:
                #     # self.fields[field].disabled = True

        if self.instance and self.instance.status == 'sent':
            for field in self.fields:
                if field not in ['status', 'protocol']:
                    self.fields[field].disabled = True

        self.fields['title'].widget.attrs['autofocus'] = True
        self.fields['title'].widget.attrs = {
            'class': 'form-control',
            'autocomplete': 'off',
            'id': 'title',
            'data-target': '#title',
            'placeholder': 'Escreva o assunto da carta'
        }
        self.fields['job'].widget.attrs = {
            'class': 'form-control',
            'autocomplete': 'off',
            'id': 'job',
            'data-target': '#job',
            'placeholder': 'Escreva a função do destinatário'
        }
        self.fields['city'].widget.attrs = {
            'class': 'form-control',
            'autocomplete': 'off',
            'id': 'city',
            'data-target': '#city',
            'placeholder': 'Escreva a cidade destinatário'
        }
        self.fields['recipient'].widget.attrs = {
            'class': 'form-control',
            'autocomplete': 'off',
            'id': 'recipient',
            'data-target': '#recipient',
            'placeholder': 'Escreva o nome do destinatário'
        }
        self.fields['entity'].widget.attrs = {
            'class': 'form-control',
            'autocomplete': 'off',
            'id': 'entity',
            'data-target': '#entity',
            'placeholder': 'Escreva o orgão do destinatário'
        }
        self.fields['content'].widget.attrs = {
            'class': 'form-control',
            'autocomplete': 'off',
            'id': 'content',
            'data-target': '#content',
            'placeholder': 'Escreva o corpo da carta',
            'cols': 79,
            'rows': 15
        }
        self.fields['status'].widget.attrs = {
            'class': 'form-control',
            'autocomplete': 'off',
            'id': 'status',
            'data-target': '#status',
        }
        self.fields['date_sent'].widget.attrs = {
            'class': 'form-control datetimepicker-input',
            'autocomplete': 'off',
            'id': 'date_sent',
            'data-target': '#date_sent',
            'data-toggle': 'datetimepicker'
        }
        self.fields['protocol'].widget.attrs = {
            'class': 'form-control',
            'autocomplete': 'off',
            'id': 'protocol',
            'data-target': '#protocol',
        }

        letter = kwargs.get('instance', None)  # Obtenha a instância da carta


        # Verificação de status e se o usuário é o autor da carta
        if letter and letter.status == 'approved':
            # Se a carta foi aprovada e o usuário é o autor, permitimos que o status "Enviada" seja selecionado
            if letter.user_created == user:  # Verifica se o usuário é o autor
                self.fields['status'].choices = [
                    ('approved', 'Aprovada'),
                    # ('sent', 'Enviada'),  # Autor pode enviar a carta
                ]
            else:
                # Usuários que não são autores, mas têm permissão para ver o status "Aprovada"
                self.fields['status'].choices = [
                    ('approved', 'Aprovada'),
                ]
        elif letter and letter.status == 'rejected':
            self.fields['status'].choices = [
                ('drafted', 'Rascunho'),
                ('submitted', 'Submetida para Aprovação'),
                ('rejected', 'Rejeitada'),
            ]

        # Verifique se o usuário é do grupo DIREÇÃO ou ADMINISTRADOR
        if user.groups.filter(name='DIREÇÃO').exists() or user.groups.filter(name='ADMINISTRADOR').exists():
            self.fields['status'].choices = [
                ('drafted', 'Rascunho'),
                ('submitted', 'Submetida para Aprovação'),
                ('approved', 'Aprovada'),
                ('rejected', 'Rejeitada'),
            ]
        elif user.groups.filter(name='GESTOR').exists() and letter and letter.user_created != user:
            self.fields['status'].choices = [
                # ('drafted', 'Rascunho'),
                ('submitted', 'Submetida para Aprovação'),
                ('approved', 'Aprovada'),
                ('rejected', 'Rejeitada'),
            ]
        elif user.groups.filter(name='GESTOR').exists() and letter and letter.user_created == user:
            self.fields['status'].choices = [
                ('drafted', 'Rascunho'),
                ('submitted', 'Submetida para Aprovação'),
                ('approved', 'Aprovada'),
                ('rejected', 'Rejeitada')
            ]
        elif user.groups.filter(name='COLABORADOR').exists():
            self.fields['status'].choices = [
                ('drafted', 'Rascunho'),
                ('submitted', 'Submetida para Aprovação'),
            ]
        else:
            # Colaboradores só podem ver seus rascunhos ou cartas submetidas
            if user.groups.filter(name='COLABORADOR').exists() and letter and letter.user_created == user:
                self.fields['status'].choices = [
                    ('drafted', 'Rascunho'),
                    ('submitted', 'Submetida para Aprovação'),
                ]
            # else:
            #     self.fields['status'].choices = [
            #         ('drafted', 'Rascunho'),
            #         ('submitted', 'Submetida para Aprovação'),
            #     ]

        # Adiciona o status "Enviada" somente se a carta foi aprovada e o usuário é o autor
        if letter and letter.status == 'approved' and letter.user_created == user:
            self.fields['status'].choices += [('sent', 'Enviada')]

        #
        # # Se a carta já estiver cancelada, todos podem ver o status "cancelado"
        # if letter and letter.status == 'approved':
        #     self.fields['status'].choices = [
        #         ('sent', 'Enviada'),
        #         ('approved', 'Aprovada'),
        #     ]
        #     # Se a carta já estiver cancelada, todos podem ver o status "cancelado"
        # elif letter and letter.status == 'rejected':
        #         self.fields['status'].choices = [
        #             ('drafted', 'Rascunho'),
        #             ('submitted', 'Submetida para Aprovação'),
        #             ('rejected', 'Rejeitada'),
        #         ]
        # else:
        #     # Defina as opções de status com base no grupo do usuário
        #     if user.groups.filter(name='DIREÇÃO').exists() or user.groups.filter(name='ADMINISTRADOR').exists():
        #         # Direção e administradores podem ver todos os status
        #         self.fields['status'].choices = [
        #             ('drafted', 'Rascunho'),
        #             ('submitted', 'Submetida para Aprovação'),
        #             ('approved', 'Aprovada'),
        #             ('sent', 'Enviada'),
        #             ('rejected', 'Rejeitada'),
        #         ]
        #     elif user.groups.filter(name='GESTOR').exists() :
        #         # Gestores podem aprovar, rejeitar ou ver cartas submetidas
        #         # Se o usuário não for o proprietário, remove o status 'Enviada' do campo de status
        #
        #         self.fields['status'].choices = [
        #             ('submitted', 'Submetida para Aprovação'),
        #             ('approved', 'Aprovada'),
        #             ('sent', 'Enviada'),
        #             ('rejected', 'Rejeitada'),
        #             # ('drafted', 'Rascunho'),
        #         ]
        #
        #     else:
        #         # Colaboradores só podem trabalhar com rascunhos ou submeter cartas
        #         self.fields['status'].choices = [
        #             ('drafted', 'Rascunho'),
        #             ('submitted', 'Submetida para Aprovação'),
        #             ('sent', 'Enviada'),
        #         ]
        #


    class Meta:
        model = Letter
        fields = "__all__"
        exclude = ['user_created', 'reference_code', 'user_updated', 'coment_review', 'department']
        widgets = {
            'title': TextInput(
                attrs={
                    'placeholder': 'Escreva o assunto da carta'
                }
            ),

            'date_sent': DateInput(
                format='%Y-%m-%d',
                attrs={
                    'class': 'form-control datetimepicker-input',
                    'autocomplete': 'off',
                    'id': 'date_sent',
                    'data-target': '#date_sent',
                    'data-toggle': 'datetimepicker'

                }),

            'status': Select(

                attrs={
                    'class': 'form-control',
                    'autocomplete': 'off',
                    'id': 'status',
                    'data-target': '#status',

                }),

            # 'content': CKEditorWidget(
            #
            #     attrs={
            #         'class': 'django_ckeditor_5',
            #         'autocomplete': 'off',
            #         'id': 'content',
            #         'data-target': '#content',
            #
            #     }, config_name='Conteúdo'
            #
            # ),

            'coment_rejected': Textarea(
                attrs={
                    'id': 'coment_rejected',
                    'data-target': '#coment_rejected',
                    'placeholder': 'Escreva os comentários',

                    'rows': 10,
                    'cols': 10
                }
            )


        }

    def save(self, commit=True):
        data = {}
        form = super()
        try:
            if form.is_valid():

                form.save()
            else:
                data['error'] = form.errors
        except Exception as e:
            data['error'] = str(e)
        return data

    def clean(self):
        cleaned_data = super().clean()
        user = get_current_user()
        status = cleaned_data.get('status')
        comentarios = cleaned_data.get('coment_rejected')
        protocol = cleaned_data.get('protocol')

        print(comentarios, 'coment')
       # print(status, 'coment 1')

        if status == 'rejected' and not comentarios:
            # raise ValidationError('Comentários são obrigatórios quando o status é rejeitado.')
            self.add_error('coment_rejected', 'Comentários são obrigatórios quando o status é rejeitado.')

            # Verifique se o status é "cancelada"
        if status == 'rejected':
            # Apenas usuários da Direção, Gestores ou Administradores podem cancelar
            if not (user.groups.filter(name__in=['DIREÇÃO', 'ADMINISTRADOR', 'GESTOR']).exists()):
                self.add_error('status', 'Você não tem permissão para rejeitar esta carta, por favor corrija os erros e Submeta ou guarde como Rascunho.')
        letter = self.instance # Obtenha a instância da carta
        print(letter.status)
        if (status == 'sent' and letter.status == 'drafted') or (letter.status == 'submited' and status == 'sent'):
            # Apenas usuários da Direção, Gestores ou Administradores podem cancelar
            if not (user.groups.filter(name__in=['DIREÇÃO', 'ADMINISTRADOR', 'GESTOR']).exists()):
                self.add_error('status', 'Você não tem permissão para enviar esta carta, por favor Submeta para Aprovação.')

                # Verifique se a carta foi aprovada e o status está sendo alterado para enviado
                if self.instance.status == 'approved' and status == 'sent' and not protocol:
                    raise ValidationError({
                        'protocol': "O upload do protocolo é obrigatório ao enviar a carta."
                    })

                # Verifica se o status foi alterado incorretamente
                if self.instance.status == 'approved' and status != 'sent':
                    raise ValidationError({
                        'status': "Você só pode alterar o status para 'enviado' após a aprovação."
                    })
        return cleaned_data


# class LetterForm1(ModelForm):
#     class Meta:
#         model = Letter
#         fields = ['title', 'content', 'status']
#
#     def __init__(self, *args, **kwargs):
#         user = kwargs.pop('user', None)  # Recebe o usuário na inicialização do formulário
#         super(LetterForm, self).__init__(*args, **kwargs)
#
#         # Defina as opções de status com base no grupo do usuário
#         if user.groups.filter(name='DIREÇÃO').exists() or user.groups.filter(name='ADMINISTRADOR').exists():
#             # Direção e administradores podem ver todos os status
#             self.fields['status'].choices = [
#                 ('drafted', 'Rascunho'),
#                 ('submitted', 'Submetida'),
#                 ('approved', 'Aprovada'),
#                 ('rejected', 'Rejeitada'),
#             ]
#         elif user.groups.filter(name='GESTOR').exists():
#             # Gestores podem aprovar, rejeitar ou ver cartas submetidas
#             self.fields['status'].choices = [
#                 ('submitted', 'Submetida'),
#                 ('approved', 'Aprovada'),
#                 ('rejected', 'Rejeitada'),
#             ]
#         else:
#             # Colaboradores só podem trabalhar com rascunhos ou submeter cartas
#             self.fields['status'].choices = [
#                 ('drafted', 'Rascunho'),
#                 ('submitted', 'Submetida'),
#             ]


class LetterApprovalForm(ModelForm):

    def __init__(self, *args, **kwargs):
        super(LetterApprovalForm, self).__init__(*args, **kwargs)
        self.fields['coment_rejected'].required = False
        self.fields['coment_review'].required = False

    class Meta:
        model = Letter
        fields = "__all__"
        exclude = ['user_created', 'reference_code', 'user_updated', 'coment_review', 'department']
        widgets = {
            'title': TextInput(
                attrs={
                    'placeholder': 'Escreva o assunto da carta'
                }
            ),

            'date_sent': DateInput(
                format='%Y-%m-%d',
                attrs={
                    'class': 'form-control datetimepicker-input',
                    'autocomplete': 'off',
                    'id': 'date_sent',
                    'data-target': '#date_sent',
                    'data-toggle': 'datetimepicker'

                }),

            'status': Select(
                attrs={
                    'class': 'form-control',
                    'autocomplete': 'off',
                    'id': 'status',
                    'data-target': '#status',

                }),

            'content': Textarea(
                attrs={
                    'id': 'content',
                    'data-target': '#content',
                    'placeholder': 'Insira a descrição do departamento (Opcional)',
                    'rows': 10,
                    'cols': 40,
                }
            )
        }

    def clean(self):
        cleaned_data = super().clean()
        status = cleaned_data.get('status')
        comentario_rejeicao = cleaned_data.get('coment_rejected')

        if status == 'rejeitada' and not comentario_rejeicao:
            self.add_error('coment_rejected', 'Por favor, forneça um comentário para a rejeição.')

        return cleaned_data

    def save(self, commit=True):
        data = {}
        form = super()
        try:
            if form.is_valid():

                form.save()
            else:
                data['error'] = form.errors
        except Exception as e:
            data['error'] = str(e)
        return data
