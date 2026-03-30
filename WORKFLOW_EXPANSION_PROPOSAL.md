# 📋 Proposta de Expansão do Workflow (Pós-Aprovação)

Este documento descreve as duas abordagens possíveis para implementar os estados **`ORDERED`**, **`PARTIALLY_RECEIVED`** e **`COMPLETED`** na plataforma de Requisições de Compra.

---

## 🔌 Opção A: Integração com ERP Primavera (Automática)

Esta é a solução ideal a longo prazo, onde o sistema de requisições comunica diretamente com o software de gestão da empresa.

### 🔹 Como Funciona:
1. **Aprovação Final:** A requisição atinge o estado `APPROVED` ou `PARTIALLY_APPROVED`.
2. **Sincronização:** O backend envia os dados da requisição via API para o ERP Primavera (ex: criando um *Documento de Compra* ou *Ordem de Compra*).
   * O campo `erp_sync_status` muda para `SYNCED`.
3. **Mapeamento de Estados:**
   * **`ORDERED`:** Quando a nota de encomenda é emitida no Primavera, um *Webhook* atualiza o backend para `ORDERED`.
   * **`PARTIALLY_RECEIVED`:** Quando há entradas parciais de armazém no Primavera.
   * **`COMPLETED`:** Quando a guia de remessa/fatura é totalmente conferida no Primavera.

### ✅ Vantagens:
* **Zero Retrabalho:** A Central de Compras não precisa de introduzir dados duas vezes.
* **Dados Reais:** Reflete exatamente o que está no sistema financeiro/logístico.
* **Automação:** Atualização em tempo real sem intervenção humana no portal.

---

## ✍️ Opção B: Gestão Manual no Portal (Sem ERP)

Solução recomendada para arrancar já, onde a Central de Compras faz a gestão dos estados diretamente na interface.

### 🔹 Fase 1: Registo de Encomenda (`ORDERED`)
* **Fluxo:** Central de Compras clica num botão **"Registar Encomenda"** na requisição aprovada.
* **Ação:** Abre um modal para inserir o Número da Encomenda (PO) e muda o status para `ORDERED`.
* **Benefício:** Dá visibilidade imediata ao solicitante de que a compra está no fornecedor.

### 🔹 Fase 1.1: Receção Global Leve (`COMPLETED`)
* **Fluxo:** Botão **"Confirmar Receção Global"** ativo em PRs `ORDERED`.
* **Ação:** Um clique muda para `COMPLETED` ("Chegou tudo").
* **Benefício:** Fecha o ciclo a 100% sem complexidade de tabelas ou stocks.

### 🔹 Fase 2: Receção Detalhada (Item a Item)
* **Estrutura:** Criar tabela de Entregas (`ItemReceipt`) para controlar quantidades (`PARTIALLY_RECEIVED`).
* **Lógica:** 
  * `soma_recebido < aprovado` $\rightarrow$ `PARTIALLY_RECEIVED`
  * `todos os itens recebidos` $\rightarrow$ `COMPLETED`
* **Benefício:** Controlo real de backlog e entregas em falta.

---

## ⚖️ Tabela Comparativa

| Característica | Opção A (Com Primavera) | Opção B (Manual) |
| :--- | :--- | :--- |
| **Esforço de Dev** | Alto (API Primavera) | Médio (Novas telas/lógicas) |
| **Retrabalho** | Nenhum | Algum (Alimentar 2 sistemas) |
| **Precisão** | Máxima | Depende da disciplina humana |
| **Velocidade de Entrega** | Lenta | Rápida (Fase 1) |

---
*Nota: Este documento serve de especificação para futuro desenvolvimento.*
