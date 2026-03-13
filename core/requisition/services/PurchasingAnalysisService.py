# services/PurchasingAnalysisService.py
from decimal import Decimal
from django.conf import settings


class PurchasingAnalysisService:
    """
    Serviço responsável pelas regras de negócio da Central de Compras
    """

    def __init__(self, purchase_request):
        self.request = purchase_request
        # Configurable threshold via settings.DIRECTOR_THRESHOLD
        try:
            self.company_limit = Decimal(str(getattr(settings, 'DIRECTOR_THRESHOLD', '5000000.00')))
        except Exception:
            self.company_limit = Decimal('5000000.00')
        # max items_missing_details to return (configurable)
        try:
            self.missing_items_limit = int(getattr(settings, 'REQ_ANALYZE_MISSING_LIMIT', 200))
        except Exception:
            self.missing_items_limit = 200

    def requires_director_approval(self):
        """
        REGRA DE NEGÓCIO: Decidir se a requisição precisa ir para direção

        Critérios atuais:
        1. Valor total > 5.000.000 Kz

        Returns: (bool, str) - (precisa, motivo)
        """
        motivos = []

        # ----- REGRA 1: Valor total acima do limite -----
        if self.request.total_amount and self.request.total_amount > self.company_limit:
            motivos.append(
                f"Valor total ({self.format_currency(self.request.total_amount)}) "
                f"excede {self.format_currency(self.company_limit)}"
            )

        # NOTA: Futuramente podes adicionar mais regras aqui:
        # - Categorias especiais (quando implementares ItemCategory)
        # - Departamentos específicos
        # - Projetos estratégicos

        if motivos:
            return True, "; ".join(motivos)

        return False, "Não requer aprovação da direção"

    def can_edit_request(self, user):
        """
        Verifica se user pode editar a requisição
        - Central de Compras pode editar se requisição está em análise
        """
        if not user.is_purchasing_central:
            return False, "Apenas Central de Compras pode editar"

        if self.request.status not in ['PENDING_PURCHASING', 'PENDING_DIRECTOR_APPROVAL']:
            return False, f"Não é possível editar requisição com status {self.request.status}"

        return True, "Pode editar"

    def calculate_totals(self):
        """
        Recalcula totais da requisição baseado nos itens
        """
        total = Decimal('0.00')
        items_with_price = 0
        items_with_supplier = 0

        for item in self.request.items.all():
            if item.total_price:
                total += item.total_price
                items_with_price += 1
            if getattr(item, 'preferred_supplier', None):
                items_with_supplier += 1

        return {
            'total_amount': total,
            'items_with_price': items_with_price,
            'total_items': self.request.items.count(),
            'has_items_without_price': items_with_price < self.request.items.count(),
            'items_with_supplier': items_with_supplier,
            'has_items_without_supplier': items_with_supplier < self.request.items.count(),
            'items_without_supplier_count': self.request.items.count() - items_with_supplier,
        }

    def analyze_request(self):
        """
        Análise completa da requisição para a Central de Compras
        """
        totals = self.calculate_totals()
        precisa_direcao, motivo = self.requires_director_approval()

        # Build list of missing item details (id, description, missing: ['price','supplier'], quantity, current_unit_price)
        items_missing = []
        try:
            # Use values() to avoid full model instantiation for performance
            qs = self.request.items.all().values('id', 'description', 'quantity', 'unit_price', 'preferred_supplier')
            for row in qs:
                missing = []
                if row.get('unit_price') is None:
                    missing.append('price')
                # preferred_supplier: consider empty/blank as missing
                ps = row.get('preferred_supplier')
                if not ps or (isinstance(ps, str) and ps.strip() == ''):
                    missing.append('supplier')

                if missing:
                    items_missing.append({
                        'item_id': row.get('id'),
                        'description': row.get('description'),
                        'missing': missing,
                        'quantity': row.get('quantity'),
                        'current_unit_price': row.get('unit_price')
                    })
        except Exception:
            items_missing = []

        # total missing count and truncation
        items_missing_total = len(items_missing)
        items_missing_truncated = False
        if items_missing_total > self.missing_items_limit:
            items_missing = items_missing[:self.missing_items_limit]
            items_missing_truncated = True

        return {
            'request_id': self.request.id,
            'code': self.request.code,
            'context': self.request.context_type,
            'project': self.request.project.name if self.request.project else None,
            'department': self.request.effective_department.name if self.request.effective_department else None,

            # Análise de valores
            'total_amount': totals['total_amount'],
            'formatted_total': self.format_currency(totals['total_amount']),
            'items_count': totals['total_items'],
            'items_with_price': totals['items_with_price'],
            'has_incomplete_items': totals['has_items_without_price'],
            'items_with_supplier': totals['items_with_supplier'],
            'has_items_without_supplier': totals['has_items_without_supplier'],
            'items_without_supplier_count': totals['items_without_supplier_count'],
            'items_missing_details': items_missing,
            'items_missing_total': items_missing_total,
            'items_missing_truncated': items_missing_truncated,

            # Decisão
            'requires_director_approval': precisa_direcao,
            'director_approval_reason': motivo,
            'company_limit': self.company_limit,
            'formatted_limit': self.format_currency(self.company_limit),

            # Status atual
            'current_status': self.request.status,
            'submitted_at': self.request.submitted_at,

            # Recomendação
            'recommendation': self._get_recommendation(precisa_direcao),
        }

    def _get_recommendation(self, precisa_direcao):
        """Retorna recomendação baseada na análise"""
        if precisa_direcao:
            return {
                'action': 'FORWARD_TO_DIRECTOR',
                'message': 'Encaminhar para aprovação da Direção',
                'reason': 'Requer aprovação da direção conforme regras de negócio'
            }
        else:
            return {
                'action': 'APPROVE',
                'message': 'Aprovar diretamente',
                'reason': 'Não requer aprovação da direção'
            }

    @staticmethod
    def format_currency(value):
        """Formata valor em moeda local"""
        if value is None:
            return "0,00 Kz"
        try:
            return f"{value:,.2f} Kz".replace(",", " ").replace(".", ",")
        except:
            return f"{value} Kz"