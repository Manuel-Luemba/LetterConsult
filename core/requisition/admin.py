from django.contrib import admin
from .models import PurchaseRequest, PurchaseRequestItem

# Inline para os itens dentro da requisição
class PurchaseRequestItemInline(admin.TabularInline):
    model = PurchaseRequestItem
    extra = 1  # quantos itens vazios aparecem por padrão
    fields = ("description", "quantity", "unit_price", "special_status", "observations")
    readonly_fields = ("total_price",)  # calculado automaticamente
    show_change_link = True


@admin.register(PurchaseRequest)
class PurchaseRequestAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "code",
        "context_type",
        "project",
        "department",
        "requested_by",
        "status",
        "total_amount",
        "request_date",
    )
    list_filter = ("status", "context_type", "project", "department")
    search_fields = ("id", "project__name", "department__name", "requested_by__username")
    inlines = [PurchaseRequestItemInline]
    readonly_fields = ("created_at", "updated_at", "submitted_at", "completed_at", "code")


@admin.register(PurchaseRequestItem)
class PurchaseRequestItemAdmin(admin.ModelAdmin):
    list_display = (
        "purchase_request",
        "description",
        "quantity",
        "urgency_level",
        "unit_price",
        "total_price",
        "special_status",
    )
    list_filter = ("special_status",)
    search_fields = ("description", "purchase_request__id", "purchase_request__code")
    readonly_fields = ("total_price",)