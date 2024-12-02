# gender = models.CharField(max_length=20, blank=True, null=True, choices=gender, default="Selecione o género")
# phone = models.CharField(max_length=20, verbose_name='telefone', blank=True, null=True)
# department = models.ForeignKey(Department, on_delete=models.CASCADE, null=True, blank=True)
# position = models.ForeignKey(Position, on_delete=models.CASCADE, blank=True, null=True)
# max_days_ayer = models.PositiveIntegerField(default=22)
# dias_ferias_disponiveis = models.PositiveIntegerField(default=max_days_ayer)
# used_days = models.PositiveIntegerField(default=0)
# hold_days = models.PositiveIntegerField(default=0)

# def get_group_session(self):
#     try:
#         request = get_current_request()
#         groups = self.groups.all()
#         if groups.exists():
#             if 'group' not in request.session:
#                 request.session['group'] = groups[0]
#     except:
#         pass
#
# def atualizar_ferias_anuais(self):
#     # Calcula o total de dias de ausência aprovados para o usuário
#     total_ausencias_aprovadas = Absence.objects.filter(
#         Employee=self.user, status='Aprovado'
#     ).aggregate(total_dias=Sum(F('data_fim') - F('data_inicio'), output_field=DurationField()))[
#                                     'total_dias'] or timedelta(days=0)
#
#     # Considera o limite máximo de 22 dias por ano
#     #dias_maximos_por_ano = 22
#
#     # Calcula os dias acumulados do ano anterior (se houver)
#     dias_acumulados_anterior = self.dias_ferias_disponiveis - self.dias_maximos_por_ano
#     if dias_acumulados_anterior < 0:
#         dias_acumulados_anterior = 0
#
#     # Atualiza o saldo de férias anuais
#     self.dias_ferias_disponiveis = max(0,
#                                        dias_acumulados_anterior + self.dias_maximos_por_ano - total_ausencias_aprovadas.days)
#     self.save()
# #
# def calcular_dias_disponiveis(self):
#     total_dias_disponiveis = self.dias_ferias_disponiveis
#     ano_atual = date.today().year
#     ausencias_ano_atual = Absence.objects.filter(data_inicio__year=ano_atual, Employee=self.user, status='Aprovado')
#     for ausencia in ausencias_ano_atual:
#         total_dias_disponiveis -= (ausencia.data_fim - ausencia.data_inicio).days
#     self.dias_ferias_disponiveis = max(0, total_dias_disponiveis)
#     self.save()

#
# def notificacao_ferias_seis_meses(self):
#     # Calcula a data há 6 meses atrás
#     data_seis_meses_atras = date.today() - timedelta(days=180)
#
#     # Filtra as ausências nos últimos 6 meses
#     ausencias_seis_meses = Absence.objects.filter(data_inicio__gte=data_seis_meses_atras)
#
#     # Calcula o total de dias de ausência nos últimos 6 meses
#     total_dias_ausencia_seis_meses = sum(
#         (ausencia.data_fim - ausencia.data_inicio).days + 1 for ausencia in ausencias_seis_meses)
#
#     # Calcula os dias disponíveis de férias atualmente
#     dias_disponiveis = self.calcular_dias_disponiveis()
#
#     # Verifica se o funcionário tem mais de 22 dias de férias disponíveis após 6 meses
#     if total_dias_ausencia_seis_meses == 0 and dias_disponiveis > 22:
#         # Envia a notificação para o funcionário
#         Notification.objects.create(
#             funcionario=self,
#             mensagem=f"Você tem mais de 22 dias de férias disponíveis após 6 meses. Por favor, planeje suas férias."
#         )
#