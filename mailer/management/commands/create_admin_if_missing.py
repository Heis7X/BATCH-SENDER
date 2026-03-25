from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model


class Command(BaseCommand):
    help = "Create an admin user if it does not already exist"

    def handle(self, *args, **options):
        User = get_user_model()

        username = "admin"
        email = "joilaandri@gmail.com"
        password = "ChangeMe123!"

        if User.objects.filter(username=username).exists():
            self.stdout.write(self.style.WARNING("Admin already exists"))
            return

        User.objects.create_superuser(
            username=username,
            email=email,
            password=password,
        )

        self.stdout.write(self.style.SUCCESS("Admin created successfully"))