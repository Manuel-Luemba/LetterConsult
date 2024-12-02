from django import forms
from django.core.exceptions import ValidationError
from django.forms import ModelForm, TextInput, PasswordInput, EmailInput, SelectMultiple, Select

from core.user.models import User


class UserForm(ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['first_name'].widget.attrs['autofocus'] = True

    class Meta:
        model = User
        fields = 'first_name', 'last_name', 'email', 'username', 'password', 'image', 'groups', 'position', 'department'
        widgets = {
            'first_name': forms.TextInput(
                attrs={
                    'required': True,
                    'placeholder': 'Digite seu nome',
                    'id': 'first_name',
                    'data-target': '#first_name'

                }
            ),
            'last_name': forms.TextInput(
                attrs={
                    'required': True,
                    'placeholder': 'Digite seu sobrenome',
                    'id': 'last_name',
                    'data-target': '#last_name'
                }
            ),
            'email': forms.EmailInput(
                attrs={
                    'required': True,
                    'placeholder': 'Digite seu email',
                    'id': 'email',
                    'data-target': '#email'
                }
            ),
            'username': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'style': 'width: 100%',
                    'required': True,
                    'placeholder': 'Digite seu nome de usuário',
                    'id': 'username',
                    'data-target': '#username'
                }
            ),
            'password': forms.PasswordInput(render_value=True,
                                            attrs={
                                                'class': 'form-control',
                                                'style': 'width: 100%',
                                                'required': True,
                                                'placeholder': 'Digite sua password',
                                                'id': 'password',
                                                'data-target': '#password'
                                            }
                                            ),
            'groups': forms.SelectMultiple(attrs={
                'required': True,
                'class': 'form-control select2',
                'style': 'width: 100%',
                'multiple': 'multiple',
                'id': 'groups',
                'data-target': '#groups'
            }),

            'position': Select(
                attrs={
                    'required': True,
                    'class': 'form-control select2',
                    'style': 'width: 100%',
                    'id': 'position',
                    'data-target': '#position'
                }
            ),

            'department': forms.Select(attrs={
                'required': True,
                'class': 'form-control select2',
                'style': 'width: 100%',
                'id': 'department',
                'data-target': '#department'

            })
        }
        exclude = ['user_permissions', 'last_login', 'date_joined', 'is_superuser', 'is_active', 'is_staff']

    def save(self, commit=True):
        data = {}
        form = super()

        try:
            if form.is_valid():
                pwd = self.cleaned_data['password']
                u = form.save(commit=False)
                if u.pk is None:
                    u.set_password(pwd)
                else:
                    user = User.objects.get(pk=u.pk)
                    if user.password != pwd:
                        u.set_password(pwd)
                u.save()
                u.groups.clear()
                for g in self.cleaned_data['groups']:
                    u.groups.add(g)
            else:
                data['error'] = form.errors

        except Exception as e:
            data['error'] = str(e)
        return data


    def clean(self):
        super().clean()

    # def clean_username(self):
    #     username = self.cleaned_data['username']
    #     action = self.cleaned_data['action']
    #     print(action, 'action')
    #     if User.objects.filter(username=username).exists():
    #         raise forms.ValidationError('A User with that username already exists.')
    #     return username


class UserProfileForm(ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['first_name'].widget.attrs['autofocus'] = True

    class Meta:
        model = User
        fields = 'first_name', 'last_name', 'email', 'username', 'password', 'image'
        widgets = {
            'first_name': forms.TextInput(
                attrs={
                    'placeholder': 'Ingrese sus nombre',
                }
            ),
            'last_name': forms.TextInput(
                attrs={
                    'placeholder': 'Ingrese sus apellidos',
                }
            ),
            'email': forms.EmailInput(
                attrs={
                    'placeholder': 'Ingrese su email',
                }
            ),
            'username': forms.TextInput(
                attrs={
                    'placeholder': 'Ingrese su nombre de usuario',
                }
            ),
            'password': forms.PasswordInput(render_value=True,
                                            attrs={
                                                'placeholder': 'Ingrese su password',
                                            }
                                            ),
        }
        exclude = ['user_permissions', 'groups', 'last_login', 'date_joined', 'is_superuser', 'is_active', 'is_staff']

    def save(self, commit=True):
        data = {}
        form = super()
        try:
            if form.is_valid():
                pwd = self.cleaned_data['password']

                u = form.save(commit=False)
                if u.pk is None:
                    u.set_password(pwd)
                else:
                    user = User.objects.get(pk=u.pk)
                    if user.password != pwd:
                        u.set_password(pwd)
                u.save()
            else:
                data['error'] = form.errors

        except Exception as e:
            data['error'] = str(e)
        return data
