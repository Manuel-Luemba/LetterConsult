# Guia de Integração: Sistema de Notificações Centralizado

Este documento serve como referência técnica para a equipa de Frontend implementar o novo Hub de Notificações unificado no ERP Engconsult.

## 1. Conexão WebSocket (Push)

O ERP agora utiliza um único Hub para notificações em tempo real.

- **Endpoint**: `ws://<domain>/ws/notifications/`
- **Autenticação**: Deve ser enviado o token JWT via Query Parameter.
- **Exemplo de URL**: `ws://localhost:8000/ws/notifications/?token=eyJhbGci...`

### Estrutura da Mensagem Recebida (JSON)
Sempre que ocorrer um evento relevante, o WebSocket enviará um JSON com a seguinte estrutura:

```json
{
  "type": "purchase_request.status_changed", 
  "payload": {
    "id": 123,
    "message": "A sua requisição #123 foi aprovada! ✅",
    "event_type": "RQ_APPROVED_FINAL"
  },
  "timestamp": "2026-04-01T19:30:00Z"
}
```

### Eventos Suportados
| Evento (WebSocket `type`) | Descrição |
| :--- | :--- |
| `purchase_request.assigned_to_me` | Nova requisição para aprovação |
| `purchase_request.status_changed` | Atualização genérica de estado (RQ) |
| `timesheet.submitted` | Nova timesheet para aprovação |
| `timesheet.status_changed` | Atualização de estado de timesheet |

---

## 2. API REST (Histórico e Gestão)

Para gerir as notificações persistentes, utilize a **Ninja API** em `/api/v1/notifications/`.

### Endpoints Disponíveis
- **`GET /`**: Lista as últimas 30 notificações do utilizador.
- **`GET /unread-count`**: Retorna a contagem de mensagens não lidas.
- **`POST /{id}/read`**: Marca uma notificação específica como lida.
- **`POST /read-all`**: Marca todas as notificações como lidas.
- **`DELETE /clear-all`**: Elimina todo o histórico de notificações do utilizador.

---

## 3. Sugestão de Implementação no Vue.js (Pinia)

Recomenda-se a criação de um `NotificationStore` para gerir a conexão única e o estado global.

```typescript
// stores/notificationStore.ts
export const useNotificationStore = defineStore('notification', () => {
  const notifications = ref([]);
  const unreadCount = ref(0);

  const connectWS = (token: string) => {
    const ws = new WebSocket(`ws://localhost:8000/ws/notifications/?token=${token}`);
    
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      // 1. Mostrar Toast/Som
      playNotificationSound();
      showToast(data.payload.message);

      // 2. Atualizar contadores
      fetchUnreadCount();
      
      // 3. Opcional: Adicionar ao histórico local
      notifications.value.unshift(data.payload);
    };
  };

  return { notifications, unreadCount, connectWS };
});
```

---

---

## 4. Integração de Web Push (Browser Native)

O backend agora suporta as notificações nativas do browser (Web Push VAPID).

### Fluxo de Registro
1. O frontend obtém a chave pública VAPID via: `GET /api/v1/notifications/vapid-public-key`.
2. O browser solicita permissão e gera uma `subscription`.
3. O frontend envia a `subscription` para o backend via: `POST /api/v1/notifications/subscribe`.

### Exemplo de Registro no Vue.js
```javascript
const registration = await navigator.serviceWorker.ready;
const subscription = await registration.pushManager.subscribe({
  userVisibleOnly: true,
  applicationServerKey: vapidPublicKey
});

// Enviar 'subscription' para o endpoint /subscribe
```

## 5. Estética e UX (Premium Vibes)

Para manter o padrão de excelência da plataforma:
- **Som de Notificação**: Disparar um som subtil (ex: `notification.mp3`) ao receber eventos via WebSocket.
- **Indicador Visual**: Adicionar um "ponto" (badge) vermelho no ícone do "Sininho" no Navbar.
- **Micro-interações**: Usar animações de entrada para novos itens na lista de notificações.

> [!TIP]
> Use a biblioteca `SweetAlert2` ou `Vue3-Toastify` para os popups de notificação push enquanto o utilizador navega em outras páginas.

