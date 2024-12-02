
# class LetterListView(LoginRequiredMixin, ValidatePermissionRequiredMixin, ListView):
#     model = Letter
#     template_name = 'letter/my.html'
#     permission_required = 'erp.view_letter'
#
#     @method_decorator(csrf_exempt)
#     @method_decorator(login_required)
#     def dispatch(self, request, *args, **kwargs):
#         return super().dispatch(request, *args, **kwargs)
#
#     def post(self, request, *args, **kwargs):
#         data = {}
#         try:
#             action = request.POST.get('action', None)
#             if action == 'searchdata':
#                 data = [letter.to_json() for letter in Letter.objects.all()]
#             else:
#                 data['error'] = 'Ação inválida'
#         except Exception as e:
#             data['error'] = str(e)
#         return JsonResponse(data, safe=False)
#
#     def get_queryset(self):
#         user = self.request.user
#         if user.groups.filter(name='direcao').exists() or user.groups.filter(name='administrador').exists():
#             return Letter.objects.all()  # Direção e administradores veem todas as cartas
#         elif user.groups.filter(name='gestor').exists():
#             return Letter.objects.filter(department=user.department)  # Gestores veem cartas do departamento
#         else:
#             return Letter.objects.filter(created_by=user)  # Colaboradores veem apenas suas próprias cartas
#
#     def get_context_data(self, **kwargs):
#         context = super().get_context_data(**kwargs)
#         context["title"] = 'Lista de Cartas'
#         context["entity"] = 'Carta'
#         context["table"] = 'Letter'
#         context["manager"] = 'NÃO'
#
#         context['user'] = self.request.user
#         context["create_url"] = reverse_lazy('erp:reference_search')
#         context["list_url"] = reverse_lazy('erp:letter_mylist')
#
#         # Lógica para ajustar URL e status de manager com base nos grupos
#         if self.request.user.groups.filter(name='gestor').exists():
#             context["create_url"] = reverse_lazy('erp:absence_create_aprove')
#             context["manager"] = 'SIM'
#         elif self.request.user.groups.filter(name='direcao').exists() or self.request.user.groups.filter(
#                 name='administrador').exists():
#             context["create_url"] = reverse_lazy('erp:absence_create_aprove')
#             context["manager"] = 'SIM'
#
#         return context

# class LetterCheckView(View):
#     model = Reference
#     form_class = LetterForm
#     template_name = 'letter/search.html'
#     success_url = reverse_lazy('erp:letter_create')
#     permission_required = 'erp.view_letter'
#
#     # @method_decorator(login_required)
#     # def dispatch(self, request, *args, **kwargs):
#     #     self.object = None
#     #     return super().dispatch(request, *args, **kwargs)
#
#     @csrf_exempt
#     def post(self, request):
#         print(request)
#         codigo = request.POST.get('referencia')
#         print(codigo, 'doctor')
#         try:
#
#             referencia = Reference.objects.get(reference_code=codigo)
#
#             carta_associada = Letter.objects.filter(reference_code_id__exact=referencia.id).exists()
#
#             print(carta_associada, 'carta')
#
#             # Salvando dados na sessão
#             request.session['codigo'] = codigo
#             request.session['carta_associada'] = carta_associada
#
#             return JsonResponse({
#                 'exists': True,
#                 'associado': carta_associada,
#                 'codigo': codigo,
#                 'user': request.user.get_full_name(),
#             })
#         except Reference.DoesNotExist:
#             return JsonResponse({
#                 'exists': False,
#             })
#
#     def get_context_data(self, **kwargs):
#         context = super().get_context_data(**kwargs)
#         context["title"] = 'Criar Carta'
#         context["entity"] = 'Cartas'
#         context["table"] = 'Letter'
#         context["action"] = 'add'
#         context["list_url"] = reverse_lazy('erp:reference_list')
#         context["create_url"] = reverse_lazy('erp:reference_check')
#         context['user'] = self.request.user
#         return context
