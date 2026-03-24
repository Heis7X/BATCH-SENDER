from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from mailer.models import EmailTemplate

User = get_user_model()


class Command(BaseCommand):
    help = "Create a demo admin user and starter templates for local testing."

    def add_arguments(self, parser):
        parser.add_argument("--username", default="admin")
        parser.add_argument("--email", default="admin@example.com")
        parser.add_argument("--password", default="ChangeMe123!")

    def handle(self, *args, **options):
        user, created = User.objects.get_or_create(
            username=options["username"],
            defaults={
                "email": options["email"],
                "is_staff": True,
                "is_superuser": True,
            },
        )
        if created:
            user.set_password(options["password"])
            user.is_staff = True
            user.is_superuser = True
            user.save()
            self.stdout.write(self.style.SUCCESS(f"Created admin user {user.username}"))
        else:
            self.stdout.write(f"Admin user {user.username} already exists.")

        templates = [
            (
                "Welcome message",
                "Welcome to {{app_name}}",
                "Hello {{email}},\n\nThanks for joining {{app_name}}.\n\nBest regards,\nThe team",
            ),
            (
                "Follow-up",
                "Checking in with {{email}}",
                "Hello,\n\nThis is a quick follow-up from {{app_name}}.\n\nReply any time.",
            ),
        ]
        for name, subject, body in templates:
            EmailTemplate.objects.get_or_create(name=name, defaults={"subject": subject, "body": body})
        self.stdout.write(self.style.SUCCESS("Starter templates ensured."))
