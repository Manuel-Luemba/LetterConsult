# Guia de Dockerização: Frontend Vue.js (Nginx)

Este guia destina-se à equipa de Frontend para preparar a imagem Docker e a integração com o Backend no ambiente de produção (Hostinger VPS).

## 1. Ficheiro: `Dockerfile` (na raiz do Vue)
Crie um ficheiro chamado `Dockerfile` na pasta `vue-tailwind/` com este conteúdo:

```dockerfile
# --- Stage 1: Build Stage ---
FROM node:22-slim AS build-stage
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build-only

# --- Stage 2: Production Stage ---
FROM nginx:stable-alpine AS production-stage
COPY --from=build-stage /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

## 2. Ficheiro: `nginx.conf` (na raiz do Vue)
Este ficheiro é o "maestro" que serve o frontend e faz o proxy para o backend.

```nginx
server {
    listen 80;
    server_name localhost;

    # Frontend - Serve os ficheiros estáticos buildados
    location / {
        root   /usr/share/nginx/html;
        index  index.html index.htm;
        try_files $uri $uri/ /index.html;
    }

    # API Backend (Django Ninja)
    location /api/ {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # WebSockets (Notificações em tempo real)
    location /ws/ {
        proxy_pass http://backend:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }

    # Acesso a ficheiros de Media/Static do Django
    location /media/ { alias /app/media/; }
    location /static/ { alias /app/staticfiles/; }
}
```

## 3. Integração no `docker-compose.yml`
No `docker-compose.yml` principal (na raiz do projeto PHP), adicione este serviço:

```yaml
  frontend:
    build:
      context: ./caminho_para_o_front
      dockerfile: Dockerfile
    container_name: erp_frontend
    restart: always
    ports:
      - "80:80"
    depends_on:
      - backend
    networks:
      - erp_network
```

> [!TIP]
> **HTTPS/SSL**: Para produção, deverá adicionar um container `certbot` ou configurar o Nginx para escutar na porta 443 com os certificados.
