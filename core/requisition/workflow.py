class WorkflowService:
    """Serviço atualizado com as novas regras"""

    def _definir_aprovador_departamental(self):
        """
        REGRA ATUALIZADA:
        - Projeto: Team Leader OU Responsável do Projeto (qualquer um)
        - Fora projeto: Qualquer coordenador OU adjunto do departamento
        """
        solicitante = self.requisicao.solicitante
        aprovadores_possiveis = solicitante.get_aprovadores_departamentais_possiveis()

        if not aprovadores_possiveis:
            raise Exception("Não existem aprovadores configurados para esta requisição")

        # NÃO escolhemos um específico - o workflow aceita QUALQUER UM deles
        # Isto é gerido na view de aprovação
        return aprovadores_possiveis

    def iniciar_workflow(self):
        """Versão atualizada que lida com MÚLTIPLOS aprovadores"""

        workflow, created = WorkflowRequisicao.objects.get_or_create(
            requisicao=self.requisicao
        )

        if self.solicitante.aprova_direto_para_compras():
            # Team Leader, Responsável, Coordenador, Adjunto
            workflow.precisa_aprovacao_departamental = False
            workflow.etapa_atual = 'AGUARDANDO_APROVACAO_COMPRAS'

            # Guardamos TODOS os aprovadores possíveis?
            # Abordagem: Não guardamos, validamos na hora da aprovação
        else:
            # Administrativo ou Colaborador
            workflow.precisa_aprovacao_departamental = True
            workflow.etapa_atual = 'AGUARDANDO_APROVACAO_DEPARTAMENTAL'

            # IMPORTANTE: Não fixamos UM aprovador específico
            # A validação verifica se o aprovador está na lista de possíveis

        workflow.save()
        self.requisicao.status = 'PENDENTE'
        self.requisicao.save()

        # Notificar TODOS os aprovadores possíveis
        self._notificar_todos_aprovadores_possiveis()

        return workflow

    def _notificar_todos_aprovadores_possiveis(self):
        """Notifica TODOS que podem aprovar - evita dependência"""
        aprovadores = self.solicitante.get_aprovadores_departamentais_possiveis()

        for aprovador in aprovadores:
            # Enviar notificação: "Tens uma requisição pendente de aprovação"
            pass