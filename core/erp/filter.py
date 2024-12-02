import django_filters
from core.erp.models import Letter


class LetterFilter(django_filters.FilterSet):
    class Meta:
        model = Letter
        fields = {
            'status',

        }
