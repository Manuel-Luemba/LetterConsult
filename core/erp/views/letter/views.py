from io import BytesIO
from django.shortcuts import get_object_or_404
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse, FileResponse
from django.urls import reverse_lazy
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import ListView, CreateView, UpdateView, DetailView
from django.utils.decorators import method_decorator
from docxtpl import DocxTemplate
from spire.doc import *

from app.util import send_submission_email, send_approval_rejection_email, send_letter_sent_email_with_attachment
from core.erp.forms import ReferenceForm, LetterForm
from core.erp.mixins import ValidatePermissionRequiredMixin
from core.erp.models import Reference, Letter
from django.http import HttpResponse
from django.views.generic import View
from django.template.loader import render_to_string
from weasyprint import HTML


# USER VIEWS
class LetterMyListView(LoginRequiredMixin, ValidatePermissionRequiredMixin, ListView):
    model = Letter
    template_name = 'letter/my.html'
    permission_required = 'erp.view_letter'

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
                # Colaboradores veem apenas suas próprias cartas
                letters = Letter.objects.filter(user_created=self.request.user)

                # Converte cada carta para JSON (supondo que você tenha um método toJson() no modelo Letter)
                data = [letter.toJson() for letter in letters]

            else:
                data['error'] = 'Ocorreu um erro na requisição'
        except Exception as e:
            print(e)
            data['error'] = str(e)
        return JsonResponse(data, safe=False)

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super().get_context_data(**kwargs)
        context["title"] = 'Lista de Cartas'
        context["entity"] = 'Carta'
        context["table"] = 'Letter'
        context["create_url"] = reverse_lazy('erp:reference_search')
        context["list_url"] = reverse_lazy('erp:letter_mylist')

        return context


class LetterListView(LoginRequiredMixin, ValidatePermissionRequiredMixin, ListView):
    model = Letter
    template_name = 'letter/list.html'
    permission_required = 'erp.view_letter'

    @method_decorator(csrf_exempt)
    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        user = request.user
        data = {}
        try:
            action = request.POST.get('action', '')
            if action == 'searchdata':
                # Inicializa uma lista vazia para armazenar as cartas filtradas
                letters = []

                # Verifica se o usuário pertence a cada grupo e aplica o filtro correspondente
                if user.groups.filter(name='DIREÇÃO').exists() or user.groups.filter(name='ADMINISTRADOR').exists():
                    # Direção e administradores veem apenas cartas submetidas, aprovadas ou rejeitadas
                    letters = Letter.objects.filter(status__in=['submitted', 'approved', 'rejected', 'sent'])
                elif user.groups.filter(name='GESTOR').exists():
                    # Gestores veem cartas do seu departamento
                    letters = Letter.objects.filter(department=user.department,
                                                    status__in=['submitted', 'approved', 'rejected', 'sent'])
                else:
                    # Colaboradores veem apenas suas próprias cartas
                    letters = Letter.objects.filter(user_created=user)

                # Converte cada carta para JSON (supondo que você tenha um método toJson() no modelo Letter)
                data = [letter.toJson() for letter in letters]
            else:
                data['error'] = 'Ação inválida.'
        except Exception as e:
            data['error'] = str(e)

        return JsonResponse(data, safe=False)

    # def post(self, request, *args, **kwargs):
    #     data = {}
    #     try:
    #         action = request.POST.get('action', None)
    #         if action == 'searchdata':
    #             data = [letter.toJson() for letter in Letter.objects.all()]
    #
    #         else:
    #             data['error'] = 'Ação inválida'
    #     except Exception as e:
    #         data['error'] = str(e)
    #     return JsonResponse(data, safe=False)

    def get_queryset(self):
        user = self.request.user

        if user.groups.filter(name='DIREÇÃO').exists() or user.groups.filter(name='ADMINISTRADOR').exists():
            return Letter.objects.filter(status='submitted')  # Direção e administradores veem todas as cartas
        elif user.groups.filter(name='GESTOR').exists():
            return Letter.objects.filter(department=user.department)  # Gestores veem cartas do departamento
        else:
            return Letter.objects.filter(user_created=user)  # Colaboradores veem apenas suas próprias cartas

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = 'Lista de Cartas'
        context["entity"] = 'Carta'
        context["table"] = 'Letter'
        context["list_url"] = reverse_lazy('erp:letter_list')
        return context


class ReferenceSearchView(LoginRequiredMixin, ValidatePermissionRequiredMixin, CreateView):
    model = Reference
    form_class = ReferenceForm
    template_name = 'letter/search.html'
    success_url = reverse_lazy('erp:letter_create')
    # permission_required = 'erp.create_letter'
    # permission_required = 'homepage.aprove_absence'
    permission_required = 'erp.add_letter'

    # @method_decorator(login_required)
    # def dispatch(self, request, *args, **kwargs):
    #     self.object = None
    #     return super().dispatch(request, *args, **kwargs)

    # def post(self, request, *args, **kwargs):
    #     data = {}
    #     try:
    #         if request.POST['action'] == 'add':
    #             form = self.get_form()
    #             data = form.save()
    #         else:
    #             data['error'] = 'Não escolheu nenhuma opção válida'
    #     except Exception as e:
    #         data['error'] = str(e)
    #     return JsonResponse(data)

    @csrf_exempt
    def post(self, request):
        codigo = request.POST.get('referencia')

        try:

            referencia = Reference.objects.get(reference_code=codigo)
            referencia_id = referencia.id

            carta_associada = Letter.objects.filter(reference_code_id__exact=referencia.id).exists()
            usuario = request.user.get_full_name()
            usuario_id = request.user.id

            print(referencia_id)
            print(usuario_id)
            # Salvando dados na sessão
            request.session['codigo'] = codigo
            request.session['codigo_id'] = referencia_id
            request.session['carta_associada'] = carta_associada
            request.session['user'] = usuario
            request.session['user_id'] = usuario_id

            return JsonResponse({
                'exists': True,
                'associado': carta_associada,
                'codigo': codigo,
                'codigo_id': referencia_id,
                'user': usuario,
                'user_id': usuario_id,
            })
        except Reference.DoesNotExist:
            return JsonResponse({
                'exists': False,
            })

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = 'Pesquisar Referencias'
        context["entity"] = 'Referencias'
        context["table"] = 'Reference'
        context["action"] = 'search'
        context["list_url"] = reverse_lazy('erp:reference_list')
        context["create_url"] = reverse_lazy('erp:reference_create')
        return context


class LetterCreateView(LoginRequiredMixin, ValidatePermissionRequiredMixin, CreateView):
    model = Letter
    form_class = LetterForm
    template_name = 'letter/letter.html'
    success_url = reverse_lazy('erp:letter_mylist')
    permission_required = 'erp.add_letter'

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        self.object = None
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        data = {}
        try:
            if request.POST['action'] == 'add':
                form = self.get_form()
                if form.is_valid():

                    # Atribuindo o usuário e o código de referência a partir da sessão
                    form.instance.reference_code_id = self.request.session.get('codigo_id')  # Pega o ID da sessão
                    form.instance.department = self.request.user.department  # Pega o ID da sessão
                    # form.instance.status = 'rascunho'  # Pega o ID da sessão
                    # Salvando o formulário com as modificações
                    # form.save()
                    # data['success'] = True
                    data = form.save()
                    letter = form.instance

                    if letter.status in ['Submitted']:
                        if self.request.user.groups.filter(name='COLABORADOR').exists():
                            send_submission_email(letter)
                    # Verificar se o status foi alterado para "Aprovada" ou "Rejeitada"
                    if letter.status in ['Approved', 'Rejected']:
                        # Verificar se o criador da carta não pertence aos grupos "Direção" ou "Gestor"
                        user_groups = letter.user_created.groups.values_list('name', flat=True)
                        if 'DIREÇÃO' not in user_groups and 'GESTOR' not in user_groups:
                            send_approval_rejection_email(letter)  # Enviar o e-mail de notificação
                else:
                    data['error'] = form.errors
            else:
                data['error'] = 'Não escolheu nenhuma opção válida'
        except Exception as e:
            data['error'] = str(e)
        return JsonResponse(data)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = 'Criar Cartas'
        context["entity"] = 'Cartas'
        context["table"] = 'Letter'
        context["action"] = 'add'
        context["list_url"] = reverse_lazy('erp:letter_mylist')
        context["create_url"] = reverse_lazy('erp:letter_create')

        # Recuperando dados da sessão
        context['codigo'] = self.request.session.get('codigo')
        context['codigo_id'] = self.request.session.get('codigo_id')
        context['carta_associada'] = self.request.session.get('carta_associada')
        context['user'] = self.request.session.get('user')
        context['user_id'] = self.request.session.get('user_id')
        context["icon"] = '{}{}'.format(settings.MEDIA_URL, '/header.png')
        return context


class LetterUpdateView(LoginRequiredMixin, ValidatePermissionRequiredMixin, UpdateView):
    model = Letter
    form_class = LetterForm
    template_name = 'letter/letter.html'
    success_url = reverse_lazy('erp:letter_mylist')
    # permission_required = 'homepage.aprove_absence'
    permission_required = 'erp.change_letter'

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        data = {}
        try:
            if request.POST['action'] == 'edit':
                form = self.get_form()

                if form.is_valid():
                    data = form.save()
                    letter = form.instance
                    if letter.status in ['Submitted']:
                        if self.request.user.groups.filter(name='COLABORADOR').exists():
                            send_submission_email(letter)
                    # Verificar se o status foi alterado para "Aprovada" ou "Rejeitada"
                    if letter.status in ['Approved', 'Rejected']:
                        # Verificar se o criador da carta não pertence aos grupos "Direção" ou "Gestor"
                        user_groups = letter.user_created.groups.values_list('name', flat=True)
                        if 'DIREÇÃO' not in user_groups and 'GESTOR' not in user_groups:
                            send_approval_rejection_email(letter)  # Enviar o e-mail de notificação
                else:
                    data['error'] = form.errors

            else:
                data['error'] = 'Não escolheu nenhuma opção válida'
        except Exception as e:
            data['error'] = str(e)
        return JsonResponse(data)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = 'Editar Carta'
        context["entity"] = 'Carta'
        context["table"] = 'Letter'
        context["action"] = 'edit'
        context["list_url"] = reverse_lazy('erp:letter_mylist')
        context["edit_url"] = reverse_lazy('erp:letter_update')
        context["icon"] = '{}{}'.format(settings.MEDIA_URL, '/header.png')
        carta_id = self.kwargs['pk']
        carta = Letter.objects.get(id=carta_id)
        # Passar o estado da carta para o template
        context['carta'] = carta
        return context


class LetterDetailView(LoginRequiredMixin, ValidatePermissionRequiredMixin, DetailView):
    model = Letter
    template_name = 'letter/aval.html'
    permission_required = 'erp.view_letter'

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = 'Detalhes da Carta'
        context["entity"] = 'Carta'
        context["table"] = 'Letter'
        context["list_url"] = reverse_lazy('erp:letter_mylist')
        context["header"] = '{}{}'.format(settings.MEDIA_URL, '/header.png')

        # Recuperar a carta pelos kwargs
        carta_id = self.kwargs['pk']
        carta = Letter.objects.get(id=carta_id)

        # Passar a carta para o template
        context['carta'] = carta

        return context


# Vistas para o Chefe do Departamento
class LetterApproveView(LoginRequiredMixin, ValidatePermissionRequiredMixin, UpdateView):
    model = Letter
    form_class = LetterForm
    template_name = 'letter/letter.html'
    success_url = reverse_lazy('erp:letter_list')
    permission_required = 'erp.change_letter'

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
                letter = form.instance

                if letter.status in ['submitted']:
                    if self.request.user.groups.filter(name='COLABORADOR').exists():
                        send_submission_email(letter)
                # Verificar se o status foi alterado para "Aprovada" ou "Rejeitada"
                if letter.status in ['approved', 'rejected']:
                    # Verificar se o criador da carta não pertence aos grupos "Direção" ou "Gestor"
                    user_groups = letter.user_created.groups.values_list('name', flat=True)
                    if 'DIREÇÃO' not in user_groups or 'GESTOR' not in user_groups:
                        send_approval_rejection_email(letter)  # Enviar o e-mail de notificação
                if letter.status in ['sent']:
                    # Verificar se o criador da carta não pertence aos grupos "Direção" ou "Gestor"
                    user_groups = letter.user_created.groups.values_list('name', flat=True)
                    if 'DIREÇÃO' not in user_groups or 'GESTOR' not in user_groups:
                        send_letter_sent_email_with_attachment(letter)  # Enviar o e-mail de notificação

            else:
                data['error'] = 'Não escolheu nenhuma opção válida'
        except Exception as e:
            data['error'] = str(e)
        return JsonResponse(data)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = 'Editar Carta'
        context["entity"] = 'Carta'
        context["table"] = 'Letter'
        context["action"] = 'edit'
        context["list_url"] = reverse_lazy('erp:letter_list')
        context["edit_url"] = reverse_lazy('erp:letter_update')
        context["icon"] = '{}{}'.format(settings.MEDIA_URL, '/header.png')
        carta_id = self.kwargs['pk']
        carta = Letter.objects.get(id=carta_id)
        # Passar o estado da carta para o template
        context['carta'] = carta
        return context



class LetterDownloadView1(LoginRequiredMixin, ValidatePermissionRequiredMixin, View):
    template_path = 'media/carta_modelo.docx'
    permission_required = 'erp.add_letter'

    def get(self, request, pk):
        # Recupera a carta do banco de dados
        carta = get_object_or_404(Letter, id=pk)

        try:
            # Carrega o modelo de carta em Word
            doc = Document(self.template_path)
        except Exception as e:
            return HttpResponse(f'Erro ao carregar o modelo de carta: {str(e)}', status=500)

        # Substituições dinâmicas dos placeholders
        placeholders = {
            'entity': carta.entity.upper(),
            'job': carta.job.upper(),
            'name': carta.recipient.upper(),
            'reference': str(carta.reference_code),
            'date': carta.date_sent.strftime('%d/%m/%Y'),
            '{city}': carta.city.upper(),
            '{title}': carta.title,
            '{content}': carta.content
        }

        # # Substituir os placeholders no corpo do documento
        self.substituir_placeholders(doc, placeholders)

        # # Salva o arquivo preenchido em um BytesIO para download
        response = BytesIO()
        doc.save(response)
        response.seek(0)
        #
        # Configura a resposta HTTP para download do documento
        response_http = HttpResponse(response,
                                     content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
        response_http['Content-Disposition'] = f'attachment; filename=carta_{carta.reference_code}.docx'

        return response_http

    def substituir_placeholders(self, doc, placeholders):
        """Função para substituir placeholders no corpo do documento."""
        for paragraph in doc.paragraphs:
            for placeholder, value in placeholders.items():
                if placeholder in paragraph.text:
                    paragraph.text = paragraph.text.replace(placeholder, value)


class LetterDownloadView(View):
    def get(self, request, pk):
        # Busque os dados da tabela
        letter = get_object_or_404(Letter, id=pk)

        # Carregue o modelo
        doc_template = DocxTemplate("media/carta_modelo.docx")

        # Dados para preencher o modelo
        context = {
            'name': letter.recipient
        }

        # Renderize o documento com os dados
        doc_template.render(context)

        # Salve o documento preenchido temporariamente
        temp_path = f'media/download/temp/{letter.reference_code}.docx'
        os.makedirs(os.path.dirname(temp_path), exist_ok=True)
        doc_template.save(temp_path)

        # Carregue o documento preenchido com Spire.Doc para formatações adicionais
        document = Document()
        document.LoadFromFile(temp_path)

        # Itera por todas as seções do documento
        section = document.Sections[0]

        # Get a specific paragraph

        paragraph = section.Paragraphs[2]
        style = ParagraphStyle(document)

        style.Name = 'NewStyle'

        style.CharacterFormat.Bold = True

        style.CharacterFormat.Italic = True

        style.CharacterFormat.TextColor = Color.get_Red()

        style.CharacterFormat.FontName = 'Cambria'

        document.Styles.Add(style)

        # Apply the style to the paragraph

        # Salve o documento final
        output_path = f'media/download/{letter.user_created}/{letter.reference_code}.docx'
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        document.SaveToFile(output_path)

        # # Salva o arquivo preenchido em um BytesIO para download
        response = BytesIO()
        doc_template.save(response)
        response.seek(0)
        #
        # Configura a resposta HTTP para download do documento
        response_http = HttpResponse(response,
                                     content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
        response_http['Content-Disposition'] = f'attachment; filename=carta_.docx'

        return response_http


class ExportarCartaPDF(View):
    def get(self, request, pk):
        try:
            # Busca a carta pelo id
            carta = get_object_or_404(Letter, id=pk)
            print(carta.reference_code)
            context = {
                'carta': carta,
                'header': request.build_absolute_uri('/media/logo.png'),
                'footer': request.build_absolute_uri('/media/rodape.jpg')
            }

            # Renderiza o template com o contexto
            html_string = render_to_string('letter/pdf.html', context)

            # Configura a resposta HTTP como PDF
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = 'inline; filename=carta.pdf'

            # Gera o PDF a partir do HTML
            html = HTML(string=html_string)
            html.write_pdf(target=response)

            return response

        except Exception as e:
            # Lida com erros, caso a geração falhe
            return HttpResponse(status=500, content=f"Erro ao gerar o PDF: {e}")


class DownloadProtocolView(DetailView):
    model = Letter

    def get(self, request, *args, **kwargs):
        letter = self.get_object()
        response = FileResponse(letter.protocol.open(), as_attachment=True, filename=letter.protocol.name)
        return response
