from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create or update the NewCompany superuser account."

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            default="newcompany",
            help="Username for the administrator account.",
        )
        parser.add_argument(
            "--password",
            required=True,
            help="Password to set for the administrator account.",
        )
        parser.add_argument(
            "--email",
            default="admin@newcompany.local",
            help="Email address for the administrator account.",
        )

    def handle(self, *args, **options):
        username = options["username"].strip()
        password = options["password"]
        email = options["email"].strip()

        if not username:
            raise CommandError("Username cannot be empty.")
        if not password:
            raise CommandError("Password cannot be empty.")

        User = get_user_model()
        user, created = User.objects.get_or_create(
            username=username,
            defaults={"email": email},
        )
        if email and user.email != email:
            user.email = email

        user.is_active = True
        user.is_staff = True
        user.is_superuser = True
        user.set_password(password)
        user.save()

        action = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(f"{action} superuser account: {username}"))

