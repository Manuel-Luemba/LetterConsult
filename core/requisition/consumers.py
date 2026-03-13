import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
# Assumindo que usa a biblioteca djangorestframework-simplejwt para autenticação
from rest_framework_simplejwt.tokens import AccessToken
from django.contrib.auth import get_user_model

User = get_user_model()

class PurchaseRequestConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # Autenticação via query param ?token=...
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

        self.room_group_name = 'purchase_requests'
        # Adicionar o user ao grupo global e a um grupo privado
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.channel_layer.group_add(f"user_{self.user.id}", self.channel_name)

        await self.accept()
        print(f"WS Connected: {self.user.username}")

    async def disconnect(self, close_code):
        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)
            await self.channel_layer.group_discard(f"user_{self.user.id}", self.channel_name)

    async def receive(self, text_data):
        if text_data == 'ping':
            await self.send(text_data='pong')
            return

    # Handlers para eventos disparados via channel_layer.group_send
    async def purchase_request_event(self, event):
        """
        Generic handler for purchase request events.
        Exemplo de disparo no Django:
        channel_layer.group_send('purchase_requests', {
            'type': 'purchase_request_event',
            'data': {
                'type': 'purchase_request.created',
                'payload': {...},
                'timestamp': '...'
            }
        })
        """
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
            print(f"WS Auth Error: {e}")
            return AnonymousUser()
