from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.exceptions import TokenError
from ninja.security import HttpBearer
from django.contrib.auth import get_user_model

User = get_user_model()


class JWTAuth(HttpBearer):
    def authenticate(self, request, token: str):
        try:
            #print(f"🔑 Token recebido: {token[:50]}...")

            # Decodificar usando AccessToken do SimpleJWT
            access_token = AccessToken(token)
            user_id = access_token['user_id']
            if not user_id:
               # print("❌ Token não contém user_id")
                return None

            user = User.objects.get(id=user_id)
            #print(f"✅ Usuário autenticado: {user.username} (ID: {user.id})")
            return user

        except TokenError as e:
            print(f"❌ Token inválido: {e}")
            return None
        except User.DoesNotExist:
            #print(f"❌ Usuário não encontrado")
            return None
        except Exception as e:
            print(f"❌ Erro inesperado: {e}")
            return None
