from django.core.management.base import BaseCommand

from webroaster.access import sync_role_groups


class Command(BaseCommand):
    help = "Ensure the standard role groups exist without changing their permissions or members."

    def handle(self, *args, **options):
        groups = sync_role_groups()
        self.stdout.write(self.style.SUCCESS(f"Ensured {len(groups)} role groups exist."))
