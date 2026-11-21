from django.db.models import Case, CharField, F, Value, When
from django.utils import timezone

from .models import Contract


def contracts_with_status():
    return Contract.objects.annotate(
        effective_status=Case(
            When(
                contract_status__in=["pending", "terminated"],
                then=F("contract_status"),
            ),
            When(end_date__lt=timezone.localdate(), then=Value("expired")),
            default=Value("active"),
            output_field=CharField(),
        )
    )