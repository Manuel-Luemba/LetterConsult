from django.urls import re_path
from core.requisition import consumers

websocket_urlpatterns = [
    re_path(r'ws/purchase-requests/$', consumers.PurchaseRequestConsumer.as_asgi()),
]
