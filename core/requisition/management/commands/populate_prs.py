# cria novos PurchaseRequests clonando um PR existente e atribuindo ao user id=1
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from core.requisition.models import PurchaseRequest


class Command(BaseCommand):
    help = (
        "Popula a tabela PurchaseRequest clonando um PR existente e atribuindo ao usuário id=1. "
        "Útil para criar dados de teste de forma rápida."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--count",
            type=int,
            default=10,
            help="Número de requisições a criar (padrão 10)",
        )

    def handle(self, *args, **options):
        count = options.get("count", 10)
        User = get_user_model()
        try:
            user = User.objects.get(pk=1)
        except User.DoesNotExist:
            self.stderr.write("User with id=1 not found. Crie o user ou informe outro id.")
            return

        sample = PurchaseRequest.objects.first()
        if not sample:
            self.stderr.write(
                "Nenhuma PurchaseRequest encontrada para clonar. Crie ao menos uma PR existente antes de usar este comando."
            )
            return

        from django.forms.models import model_to_dict

        field_names = [f.name for f in PurchaseRequest._meta.fields if not f.auto_created]
        # Excluir PK pra poder criar nova instância
        if "id" in field_names:
            field_names.remove("id")
        if "pk" in field_names:
            field_names.remove("pk")

        m2m_fields = [m for m in PurchaseRequest._meta.many_to_many]

        created = []
        for i in range(count):
            data = model_to_dict(sample, fields=field_names)

            # tentar atribuir explicitamente ao user id=1 em campos comuns
            for candidate in ("created_by", "requested_by", "requester", "user", "author"):
                if candidate in data:
                    data[candidate] = user.pk

            # Ajustar ForeignKey fields: Django accepts <field>_id kwarg
            for field in list(data.keys()):
                try:
                    model_field = PurchaseRequest._meta.get_field(field)
                except Exception:
                    continue
                # se for relação estrangeira (FK) e o value é um PK, usar <field>_id
                if getattr(model_field, "is_relation", False) and not getattr(model_field, "many_to_many", False):
                    # mover para field_id
                    val = data.pop(field)
                    data[f"{field}_id"] = val

            try:
                new = PurchaseRequest.objects.create(**data)
                # copiar M2M relations (se houver)
                for m in m2m_fields:
                    try:
                        vals = getattr(sample, m.name).all()
                        getattr(new, m.name).set(vals)
                    except Exception:
                        # alguns M2M podem ser dependentes e falhar; continuamos
                        pass

                created.append(new.pk)
                self.stdout.write(self.style.SUCCESS(f'Created PR {new.pk}'))
            except Exception as e:
                self.stderr.write(self.style.ERROR(f'Failed to create PR #{i+1}: {e}'))

        self.stdout.write(self.style.NOTICE(f'Done. Created {len(created)} PR(s): {created}'))
