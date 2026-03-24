from __future__ import annotations

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models

User = get_user_model()


class EmailTemplate(models.Model):
    name = models.CharField(max_length=150, unique=True)
    subject = models.CharField(max_length=255)
    body = models.TextField()
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_templates",
    )
    updated_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="updated_templates",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class GmailConnection(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="gmail_connections")
    display_name = models.CharField(max_length=255, blank=True)
    gmail_address = models.EmailField()
    encrypted_credentials = models.TextField()
    is_active = models.BooleanField(default=True)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["gmail_address"]
        unique_together = ("user", "gmail_address")

    def __str__(self) -> str:
        return f"{self.gmail_address} ({self.user})"


class EmailBatch(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        QUEUED = "queued", "Queued"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        PARTIAL = "partial", "Partially failed"
        FAILED = "failed", "Failed"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="email_batches")
    gmail_connection = models.ForeignKey(
        GmailConnection,
        on_delete=models.PROTECT,
        related_name="batches",
    )
    template = models.ForeignKey(
        EmailTemplate,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="batches",
    )
    name = models.CharField(max_length=150, blank=True)
    subject = models.CharField(max_length=255)
    body = models.TextField()
    recipient_count = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.name or f"Batch #{self.pk}"

    @property
    def sent_count(self) -> int:
        return self.jobs.filter(status=RecipientJob.Status.SENT).count()

    @property
    def failed_count(self) -> int:
        return self.jobs.filter(status=RecipientJob.Status.FAILED).count()

    @property
    def pending_count(self) -> int:
        return self.jobs.filter(
            status__in=[RecipientJob.Status.PENDING, RecipientJob.Status.SENDING]
        ).count()


class RecipientJob(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENDING = "sending", "Sending"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"

    batch = models.ForeignKey(EmailBatch, on_delete=models.CASCADE, related_name="jobs")
    recipient_email = models.EmailField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    provider_message_id = models.CharField(max_length=255, blank=True)
    error_message = models.TextField(blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]
        unique_together = ("batch", "recipient_email")

    def __str__(self) -> str:
        return f"{self.recipient_email} - {self.status}"


class AuditLog(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_logs",
    )
    action = models.CharField(max_length=120)
    target = models.CharField(max_length=255, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.action} - {self.target}"
