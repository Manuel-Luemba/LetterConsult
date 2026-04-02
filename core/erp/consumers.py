import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.tokens import AccessToken
from django.contrib.auth import get_user_model

User = get_user_model()

class NotificationConsumer(AsyncWebsocketConsumer):
    """
    Consumer centralizado para notificações do ERP.
    Lida com eventos de diversos módulos (Timesheets, Requisições, ERP geral).
    """
    async def connect(self):
        # Autenticação via query param ?token=... (padrão usado no projeto)
        query_string = self.scope.get('query_string', b'').decode()
        token = None
        for param in query_string.split('&'):
            if param.startswith('token='):
                token = param.split('=')[1]
                break
        
        self.user = await self.get_user_from_token(token)
        
        if self.user.is_anonymous:
            await self.close()
            return

        # Cada utilizador tem o seu próprio grupo privado
        self.user_group_name = f"user_{self.user.id}"
        await self.channel_layer.group_add(self.user_group_name, self.channel_name)

        await self.accept()
        print(f"Notification WS Connected: {self.user.username} (Group: {self.user_group_name})")

    async def disconnect(self, close_code):
        if hasattr(self, 'user_group_name'):
            await self.channel_layer.group_discard(self.user_group_name, self.channel_name)

    async def receive(self, text_data):
        # Receber mensagens do frontend (ex: ping/pong ou avisos de leitura)
        try:
            data = json.loads(text_data)
            if data.get('type') == 'ping':
                await self.send(text_data=json.dumps({'type': 'pong'}))
        except Exception:
            pass

    # =========================================================================
    # HANDLERS DE EVENTOS (Chamados via channel_layer.group_send)
    # =========================================================================

    async def purchase_request_event(self, event):
        """Handler de compatibilidade para o módulo de requisições"""
        await self.send(text_data=json.dumps(event['data']))

    async def timesheet_event(self, event):
        """Handler específico para eventos de timesheet"""
        await self.send(text_data=json.dumps(event['data']))

    async def notification_event(self, event):
        """Handler genérico para notificações do novo hub"""
        await self.send(text_data=json.dumps(event['data']))

    async def notify_user(self, event):
        """Handler genérico para as notificações enviadas para o grupo user_{id}"""
        await self.send(text_data=json.dumps(event['data']))

    @database_sync_to_async
    def get_user_from_token(self, token_string):
        if not token_string:
            return AnonymousUser()
        try:
            token = AccessToken(token_string)
            user_id = token['user_id']
            return User.objects.get(id=user_id)
        except Exception as e:
            print(f"Notification WS Auth Error: {e}")
            return AnonymousUser()
