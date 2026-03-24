from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from .models import EmailBatch, EmailTemplate, GmailConnection, RecipientJob
from .services import parse_recipients, process_pending_jobs

User = get_user_model()


class RecipientParsingTests(TestCase):
    def test_parse_recipients_dedupes_and_skips_invalid_values(self):
        recipients = parse_recipients("a@example.com, bad-email\na@example.com b@example.com")
        self.assertEqual(recipients, ["a@example.com", "b@example.com"])


class ComposeBatchTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="user1", password="StrongPass123!")
        self.connection = GmailConnection.objects.create(
            user=self.user,
            gmail_address="sender@example.com",
            encrypted_credentials="placeholder",
            is_active=True,
        )
        self.template = EmailTemplate.objects.create(
            name="Starter",
            subject="Hello {{email}}",
            body="Welcome to {{app_name}}",
            is_active=True,
        )

    def test_compose_requires_login(self):
        response = self.client.get(reverse("compose_batch"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_logged_in_user_can_queue_batch(self):
        self.client.login(username="user1", password="StrongPass123!")
        response = self.client.post(
            reverse("compose_batch"),
            {
                "batch_name": "March send",
                "template": self.template.pk,
                "gmail_connection": self.connection.pk,
                "subject": "Custom subject",
                "body": "Custom body",
                "recipients_text": "alpha@example.com\nbeta@example.com",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        batch = EmailBatch.objects.get(name="March send")
        self.assertEqual(batch.recipient_count, 2)
        self.assertEqual(batch.jobs.count(), 2)
        self.assertContains(response, "Batch queued for 2 recipients")


class QueueWorkerTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="queueuser", password="StrongPass123!")
        self.connection = GmailConnection.objects.create(
            user=self.user,
            gmail_address="sender@example.com",
            encrypted_credentials="placeholder",
            is_active=True,
        )
        self.batch = EmailBatch.objects.create(
            user=self.user,
            gmail_connection=self.connection,
            name="Queue Batch",
            subject="Subject",
            body="Body",
            recipient_count=2,
            status=EmailBatch.Status.QUEUED,
        )
        RecipientJob.objects.create(batch=self.batch, recipient_email="one@example.com")
        RecipientJob.objects.create(batch=self.batch, recipient_email="two@example.com")

    @patch("mailer.services.send_gmail_message", return_value="gmail-message-123")
    def test_process_pending_jobs_marks_recipients_sent(self, _mock_send):
        processed = process_pending_jobs(limit=10, batch_id=self.batch.pk)
        self.assertEqual(processed, 2)
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.status, EmailBatch.Status.COMPLETED)
        self.assertEqual(self.batch.jobs.filter(status=RecipientJob.Status.SENT).count(), 2)
