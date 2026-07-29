import getpass

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Interactively create the private vault owner account (no public signup page exists)."

    def handle(self, *args, **options):
        User = get_user_model()

        if User.objects.exists():
            self.stdout.write(self.style.WARNING(
                "A user already exists. My Vault is designed for a single owner."
            ))
            if input("Create another user anyway? [y/N]: ").strip().lower() != "y":
                self.stdout.write("Cancelled.")
                return

        username = input("Username/email: ").strip()
        if not username:
            raise CommandError("Username/email is required.")
        if User.objects.filter(username=username).exists():
            raise CommandError(f"A user named '{username}' already exists.")

        password = self._prompt_password()

        email = username if "@" in username else ""
        user = User.objects.create_superuser(username=username, email=email, password=password)
        self.stdout.write(self.style.SUCCESS(f"Vault owner '{user.username}' created."))

    def _prompt_password(self):
        while True:
            password = getpass.getpass("Password: ")
            confirm = getpass.getpass("Confirm password: ")
            if password != confirm:
                self.stdout.write(self.style.ERROR("Passwords do not match. Try again."))
                continue
            try:
                validate_password(password)
            except ValidationError as exc:
                for message in exc.messages:
                    self.stdout.write(self.style.ERROR(message))
                continue
            return password
