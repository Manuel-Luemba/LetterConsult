# 📊 Relatório de Análise Completa: Dashboard de Requisições de Compra

Este documento apresenta um diagnóstico técnico e estratégico do Dashboard atual, com recomendações para transformá-lo numa ferramenta profissional de controlo operacional e BI para a **Central de Compras**.

---

## 📂 SEÇÃO 1: Diagnóstico Visual & UX do Dashboard Atual

O dashboard atual (`PurchaseDashboard.vue`) é predominantemente um painel de **Business Intelligence (BI)** para visualização de custos e estatísticas agregadas, em vez de uma console de operação.

| Problema | Localização | Impacto | Severidade | Sugestão |
| :--- | :--- | :--- | :--- | :--- |
| **Filtros Ocupam Muito Espaço** | `PurchaseDashboard.vue` linha 22-185 | Empurra os gráficos (KPIs) para baixo. Poluição visual imediata. | Média | Recolher filtros num painel colapsável ("Filtros Avançados") ou gaveta (Drawer). |
| **Falta de Ações Operacionais** | Estrutura Geral | A Central de Compras tem de sair do dashboard para aprovar uma RC. | **Alta** | Adicionar um painel "Ações Requeridas" (In-box) com tabela de RCs pendentes e botões rápidos. |
| **Gráficos de Custo Fixados** | `api.get('/dashboard/stats')` | Gráficos mostram apenas RCs *Aprovadas*, ignorando o backlog em análise. | Média | Permitir alternar os gráficos entre "Custo Aprovado" e "Custo Estimado (Pendente)". |
| **Falta Gráfico por Centro de Custo** | `api.py` linha 1482 | O Centro de Custo é usado apenas como **filtro**, não havendo agregação de dados para gráfico. | Média | Adicionar agregação `cost_center_costs` na API do backend para gerar gráfico de barras. |

---

## 🗺️ SEÇÃO 2: Mapeamento da Jornada do Usuário

### **Jornada: Comprador (Central de Compras)**
*   **Objetivo:** Analisar e aprovar requisições dentro do SLA.
*   **Fricção Atual:** O dashboard mostra quanto foi gasto, mas não diz explicitamente: *"Tens 5 RCs atrasadas que precisam de cotação hoje"*.
*   **Melhoria:** A página inicial do dashboard deve ser a sua **Lista de Tarefas Ordenada por Urgência**.

---

## 📈 SEÇÃO 3: KPIs Críticos & Métricas (Descoberta Crítica)

> [!CAUTION]
> **ALERTA TÉCNICO:** O backend (`api.py` linhas 1594, 1606, 1618) está a retornar valores **FIXOS (Mockados)** para métricas de tempo (SLA):
> `avg_waiting_hours: 32.5`, `avg_response_hours: 12.0`, `avg_quotation_hours: 48.0`.

### **KPIs Atuais (Já Funcionam Dinamicamente)**
*   Custo Aprovado Total & Ticket Médio.
*   Total Economia (Savings).
*   Proporção de Status (Donut).
*   Custos por Departamento / Projeto / Fornecedor Top 10.

### **Recomendação de Novos KPIs (Cálculo Real)**
*   **SLA de Aprovação:** Tempo desde `submitted_at` até `completed_at`. *(Requer correção no backend)*.
*   **Backlog de Cotação:** Número de RCs em `PENDING_PURCHASING` há mais de 48h.
*   **Conversão de Savings:** `%` de economia gerada vs Valor Inicial solicitado.

---

## 🎨 SEÇÃO 4: Redesign do Dashboard (Proposta de Layout)

O novo layout deve ser **Operacional à Esquerda / BI à Direita** (ou topo-baixo).

### **Layout Estruturado (ASCII / Mockup)**

```text
+-------------------------------------------------------------------------------+
| [Header] Dashboard de Compras | [Botão] Criar Nova RC | [Perfil]             |
+-------------------------------------------------------------------------------+
|                                                                               |
|  [Seção A: Cards de Status & KPIs Críticos]                                  |
|  +-------------+  +-------------+  +-------------+  +-------------+           |
|  | EM ATRASO   |  | PENDENTES   |  | SAVINGS     |  | SLA MÉDIO   |           |
|  |    **12**   |  |    **45**   |  | **2.5M AOA**|  |  **28h**    |           |
|  +-------------+  +-------------+  +-------------+  +-------------+           |
|                                                                               |
+-------------------------------------------------------------------------------+
|                                                                               |
|  [Seção B: Inbox de Ação Rápida] (Apenas para Central de Compras/Gerência)    |
|  +-------------------------------------------------------------------------+  |
|  | ⚠️ Requisições que precisam de sua atenção                             |  |
|  +------+-------------+----------+-----------+-----------------------------+  |
|  | ID   | Solicitante | Valor    | Prioridade| Ações                       |  |
|  +------+-------------+----------+-----------+-----------------------------+  |
|  | #102 | João Silva  | 50.000   | 🔴 ALTA   | [Aprovar] [Mais Info] [Ver] |  |
|  | #098 | Ana Costa   | 14.200   | 🟡 MÉDIA  | [Aprovar] [Mais Info] [Ver] |  |
|  +------+-------------+----------+-----------+-----------------------------+  |
|                                                                               |
+-------------------------------------------------------------------------------+
|                                                                               |
|  [Seção C: Análise Visual (BI)]                                               |
|  +-------------------------------------+  +---------------------------------+  |
|  | [Graf] Evolução de Custo Aprovado   |  | [Graf] Custos por Departamento  |  |
|  |                                     |  |                                 |  |
|  +-------------------------------------+  +---------------------------------+  |
|                                                                               |
|  > **Nota de Redesign:** Os gráficos de **Projeto** e **Centro de Custo** (Recomendado) devem ser exibidos ao lado ou num carrossel com o de Departamento, garantindo a visão tridimensional dos custos. |
```

---

## 🔄 SEÇÃO 5: Fluxos de Interação Otimizados

### **Fluxo 1: Analisar Requisição (Aprovador)**
*   **Atual:** Clica no card $\rightarrow$ Vai para lista $\rightarrow$ Procura RC $\rightarrow$ Abre Detalhe.
*   **Otimizado:** Na **Seção B (Inbox)** do Dashboard, clica em "Ver Detalhes" (abre uma gaveta lateral/drawer sem mudar de página) $\rightarrow$ Aprova diretamente. **Tempo salvo: 30-40 segundos por RC.**

---

## ✅ SEÇÃO 6: Opções Avançadas (Elevação de Padrão)

| Funcionalidade | Por que é útil | Complexidade |
| :--- | :--- | :--- |
| **Alertas de SLA** | Destacar em Vermelho as RCs em `PENDING_PURCHASING` com > 48 horas. | Baixa |
| **Exportação Personalizada** | Exportar os dados de qualquer gráfico ou tabela para Excel/PDF para reuniões. | Média |
| **Mudar Filtros para Sidebar** | Liberta espaço para focar na operação. | Média |

---

## 🛠️ SEÇÃO 7: Problemas Técnicos & Melhorias de Código

1.  **Resolver Dados Mockados (Backend):**
    *   *O que está:* `avg_waiting_hours = 32.5`
    *   *O que deve estar:* Calcular a diferença entre `ApprovalWorkflow.started_at` e `completed_at` no banco de dados.
2.  **Performance:**
    *   O endpoint `/dashboard/stats` carrega `AuditLog` e múltiplos joins. Pode ficar lento com > 10.000 registos.
    *   *Sugestão:* Indexar `status` e `request_date` (já existe nos indexes de `PurchaseRequest`), mas garantir paginação em tabelas secundárias.

---

## 📊 Roadmap de Implementação

### **FASE 1: CRÍTICA (Resolver o "Show" vs "Realidade")**
*   Substituir todos os KPIs mockados no backend por cálculos reais matemáticos agregados do banco de dados (SLA).
*   **Impacto:** Decisões baseadas em dados verdadeiros.

### **FASE 2: OPERACIONAL (UX Upgrade)**
*   Adicionar a **Tabela de Ações Pendentes (Inbox)** no centro do Dashboard.
*   Mover os filtros pesados para um botão colapsável.

### **FASE 3: BI AVANÇADO**
*   Adicionar alertas visuais de atraso (SLA violado).
*   Permitir exportação de métricas.

---
*Nota: Este documento foi gerado via Auto-Discovery do código real do sistema.*
