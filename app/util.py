from django.core.mail import send_mail
from django.conf import settings

from django.core.mail import EmailMessage  # para mandar anexos


def enviar_email_referencia(usuario, codigo_referencia):
    assunto = 'Seu Código de Referência'
    mensagem = f'Olá {usuario.get_full_name()},\n\nSeu código de referência é: {codigo_referencia}.'
    remetente = settings.DEFAULT_FROM_EMAIL
    destinatario = [usuario.email]  # E-mail do destinatário

    send_mail(assunto, mensagem, remetente, destinatario)


def send_submission_email(letter):
    manager_email = letter.user_created.department.manager.email  # Supondo que você tenha esse campo no modelo de departamento
    send_mail(
        f'Carta Submetida por {letter.user_created} ao {letter.entity}',
        f'A carta com a referencia "{letter.reference_code} " foi submetida para aprovação.',
        settings.DEFAULT_FROM_EMAIL,
        [manager_email],
        fail_silently=False,
    )


# def send_approval_rejection_email(letter):
#     status_message = "Aprovada" if letter.status == 'approved' else "Rejeitada"
#     send_mail(
#         f'Carta {status_message.capitalize()}',
#         f'A carta "{letter.title}" foi {status_message}.',
#         settings.DEFAULT_FROM_EMAIL,
#         [letter.user.email],  # Envia e-mail para o colaborador
#         fail_silently=False,
#     )



def send_approval_rejection_email(letter):
    # Verificar se a carta foi aprovada ou rejeitada
    assunto = ""
    mensagem = ""
    if letter.status in ['approved', 'rejected']:
        usuario_email = letter.user_created.email
        if letter.status == 'approved':
            assunto = "Sua carta foi aprovada"
            mensagem = f"Sua carta com a referência '{letter.reference_code}' foi aprovada."
        elif letter.status == 'rejected':
            assunto = "Sua carta foi rejeitada"
            mensagem = f"Sua carta com a referência '{letter.reference_code}' foi rejeitada."

        send_mail(
            assunto,
            mensagem,
            settings.DEFAULT_FROM_EMAIL,
            [usuario_email],
            fail_silently=False,
        )


def send_letter_sent_email_with_attachment(letter):
    department_head_email = letter.user_created.department.manager.email  # Obtenha o e-mail do chefe de departamento
    subject = f'Carta enviada'
    body = f'O colaborador "{letter.user_created.get_full_name()}" enviou a carta com a referência "{letter.reference_code}" ao {letter.entity}. O protocolo está anexado.'

    email = EmailMessage(
        subject,
        body,
        to=[department_head_email],
    )

    # Anexar o arquivo do protocolo
    if letter.protocolo_upload:
        email.attach_file(
            letter.protocol.path)  # Certifique-se de que protocolo_upload é um campo FileField ou similar

    email.send(fail_silently=False)


def get_filename(filename, request):
    return filename.upper()