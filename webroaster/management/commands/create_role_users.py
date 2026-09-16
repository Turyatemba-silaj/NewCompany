from django.core.management.base import BaseCommand

from webroaster.access import DEFAULT_PASSWORD, sync_default_role_accounts


class Command(BaseCommand):
    help = "Create default role-based staff accounts and groups."

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            default=DEFAULT_PASSWORD,
            help="Password to set for newly-created users or users without a usable password.",
        )

    def handle(self, *args, **options):
        created, updated = sync_default_role_accounts(password=options["password"])
        if created:
            self.stdout.write(self.style.SUCCESS("Created users: " + ", ".join(created)))
        if updated:
            self.stdout.write("Updated users/groups: " + ", ".join(updated))
        self.stdout.write(self.style.WARNING("Default password for new accounts: " + options["password"]))
