Requisition module — Central de Compras

Resumo das alterações relevantes para o frontend

1) Novo campo no endpoint de análise
- Endpoint: GET /api/.../central-compras/analisar/{request_id}
- Novo campo no response: `items_missing_details` (lista)

Formato de `items_missing_details` (cada item):
- item_id: integer — id do PurchaseRequestItem
- description: string|null — descrição curta do item
- missing: list[string] — motivos, valores possíveis: 'price', 'supplier'
- quantity: decimal|null
- current_unit_price: decimal|null

Exemplo de response (parsable JSON):
{
  "request_id": 42,
  "code": "RC-...",
  "total_amount": "12000.00",
  "items_count": 3,
  "items_with_price": 2,
  "items_with_supplier": 1,
  "items_missing_details": [
    {
      "item_id": 101,
      "description": "Parafuso M8 30mm",
      "missing": ["supplier"],
      "quantity": 50,
      "current_unit_price": "1000.00"
    },
    {
      "item_id": 102,
      "description": "Motor elétrico",
      "missing": ["price","supplier"],
      "quantity": 1,
      "current_unit_price": null
    }
  ],
  "requires_director_approval": false,
  "recommendation": {"action":"APPROVE","message":"Aprovar diretamente","reason":"..."}
}

2) Regras importantes (server-side)
- Solicitantes podem criar requisições e itens sem `unit_price` e sem `preferred_supplier`.
- A Central de Compras (grupo 'PurchasingCentral') deve preencher `unit_price` e `preferred_supplier` antes de aprovar.
- O servidor valida isto em `WorkflowService.approve()` e rejeitará aprovações com erro claro caso existam itens sem price ou supplier.

3) Endpoints/field mapping (frontend):
- Ao criar/editar um item via API (create/update/purchasing_edit), use os campos no item schema:
  - description, quantity, unit_price, preferred_supplier, delivery_deadline, special_status, observations
- preferred_supplier: é opcional para o solicitante (envie null/omit). A Central deve fornecer um valor não-vazio antes da aprovação.

4) Sugestões de UI
- Em tela de análise da Central, consome `items_missing_details` e destaca cada item faltante com a lista `missing`.
- Mostrar CTA direto por item: "Preencher preço" / "Selecionar fornecedor"
- Em ações em lote, antes de executar approve em lote, pedir para preencher suppliers/prices ou filtrar apenas requisições completas.

5) Testes
- Existem testes básicos de unidade em `core/requisition/tests/test_analysis.py` que validam o comportamento de análise e bloqueio de aprovação.

Se precisares, posso:
- adicionar `items_missing_details` no resultado do bulk (por requisition),
- adicionar paginação para `items_missing_details` (se houver muitos itens),
- transformar `preferred_supplier` em FK para um `Supplier` model (melhora integridade).

Obrigado — diz se queres que eu implemente o detalhe do bulk (items_missing por request em respostas de bulk) ou que eu gere documentação adicional para o front-end (OpenAPI/Swagger snippets).
