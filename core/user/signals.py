# from django.db.models.signals import pre_save
# from django.dispatch import receiver
# from core.user.models import User


# @receiver(pre_save, sender=User)
# def create_username(sender, instance, **kwargs):
#     data = {}
#     if not instance.username:
#         # Use o email como base para o nome de usuário
#         instance.username = instance.email.split('@')[0]
#     else:
#         if User.objects.filter(username=instance.username).exists():
#             data['error'] = 'Esse nome de usuário já existe.'

