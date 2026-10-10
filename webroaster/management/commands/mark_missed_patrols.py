from django.core.management.base import BaseCommand
from django.utils import timezone

from webroaster.models import PatrolSession


class Command(BaseCommand):
    help = "Mark overdue scheduled or in-progress patrol sessions as missed."

    def handle(self, *args, **options):
        now = timezone.now()
        updated = 0
        sessions = PatrolSession.objects.select_related("route").filter(status__in=("scheduled", "in_progress"))
        for session in sessions:
            if session.mark_missed_if_overdue(now):
                updated += 1
        self.stdout.write(self.style.SUCCESS(f"Marked {updated} patrol session(s) as missed."))
