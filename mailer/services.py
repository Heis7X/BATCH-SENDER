from __future__ import annotations

import base64
import csv
import io
import json
import time
from email.message import EmailMessage
from typing import Iterable

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.utils import timezone
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import Flow

from .models import AuditLog, EmailBatch, EmailTemplate, GmailConnection, RecipientJob


def log_action(user, action: str, target: str = "", payload: dict | None = None) -> None:
    AuditLog.objects.create(user=user, action=action, target=target, payload=payload or {})


class MailerConfigError(Exception):
    pass


class GmailSendError(Exception):
    pass


PLACEHOLDERS = {
    "{{app_name}}": settings.APP_NAME,
}


def _fernet() -> Fernet:
    key = settings.TOKEN_ENCRYPTION_KEY
    if not key:
        raise MailerConfigError(
            "TOKEN_ENCRYPTION_KEY is missing. Generate one with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
        )
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except Exception as exc:  # pragma: no cover - defensive
        raise MailerConfigError("TOKEN_ENCRYPTION_KEY is invalid for Fernet.") from exc


def encrypt_json(payload: dict) -> str:
    return _fernet().encrypt(json.dumps(payload).encode()).decode()


def decrypt_json(cipher_text: str) -> dict:
    try:
        raw = _fernet().decrypt(cipher_text.encode()).decode()
        return json.loads(raw)
    except (InvalidToken, json.JSONDecodeError) as exc:
        raise MailerConfigError("Saved Gmail credentials could not be decrypted.") from exc


def get_google_client_config() -> dict:
    if not settings.GOOGLE_OAUTH_CLIENT_ID or not settings.GOOGLE_OAUTH_CLIENT_SECRET:
        raise MailerConfigError(
            "Google OAuth is not configured. Set GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET."
        )
    return {
        "web": {
            "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
            "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [settings.GOOGLE_OAUTH_REDIRECT_URI],
        }
    }


def build_google_flow(*, state: str | None = None, code_verifier: str | None = None) -> Flow:
    flow = Flow.from_client_config(
        get_google_client_config(),
        scopes=settings.GOOGLE_OAUTH_SCOPES,
        state=state,
        code_verifier=code_verifier,
    )
    flow.redirect_uri = settings.GOOGLE_OAUTH_REDIRECT_URI
    return flow


def credentials_to_dict(credentials: Credentials) -> dict:
    return {
        "token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "scopes": list(credentials.scopes or settings.GOOGLE_OAUTH_SCOPES),
        "expiry": credentials.expiry.isoformat() if credentials.expiry else None,
        "id_token": getattr(credentials, "id_token", None),
    }


def fetch_google_profile(credentials: Credentials) -> dict:
    oauth2_service = build("oauth2", "v2", credentials=credentials, cache_discovery=False)
    return oauth2_service.userinfo().get().execute()


def get_connection_credentials(connection: GmailConnection) -> Credentials:
    data = decrypt_json(connection.encrypted_credentials)
    creds = Credentials(
        token=data.get("token"),
        refresh_token=data.get("refresh_token"),
        token_uri=data.get("token_uri") or "https://oauth2.googleapis.com/token",
        client_id=data.get("client_id") or settings.GOOGLE_OAUTH_CLIENT_ID,
        client_secret=data.get("client_secret") or settings.GOOGLE_OAUTH_CLIENT_SECRET,
        scopes=data.get("scopes") or settings.GOOGLE_OAUTH_SCOPES,
        id_token=data.get("id_token"),
    )
    if not creds.valid:
        if not creds.refresh_token:
            raise MailerConfigError(
                f"Gmail connection {connection.gmail_address} has no refresh token. Reconnect the account."
            )
        creds.refresh(GoogleRequest())
        connection.encrypted_credentials = encrypt_json(credentials_to_dict(creds))
        connection.last_error = ""
        connection.save(update_fields=["encrypted_credentials", "last_error", "updated_at"])
    return creds


def build_gmail_service(connection: GmailConnection):
    creds = get_connection_credentials(connection)
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def render_message_content(text: str, recipient_email: str) -> str:
    rendered = text
    for placeholder, value in PLACEHOLDERS.items():
        rendered = rendered.replace(placeholder, value)
    return rendered.replace("{{email}}", recipient_email)


def send_gmail_message(
    *,
    connection: GmailConnection,
    recipient_email: str,
    subject: str,
    body: str,
) -> str:
    gmail_service = build_gmail_service(connection)
    message = EmailMessage()
    message["To"] = recipient_email
    message["From"] = connection.gmail_address
    message["Subject"] = render_message_content(subject, recipient_email)
    message.set_content(render_message_content(body, recipient_email))

    encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
    try:
        response = (
            gmail_service.users()
            .messages()
            .send(userId="me", body={"raw": encoded_message})
            .execute()
        )
    except Exception as exc:  # pragma: no cover - external API
        connection.last_error = str(exc)
        connection.save(update_fields=["last_error", "updated_at"])
        raise GmailSendError(str(exc)) from exc

    connection.last_used_at = timezone.now()
    connection.last_error = ""
    connection.save(update_fields=["last_used_at", "last_error", "updated_at"])
    return response.get("id", "")


def _collect_csv_emails(file_bytes: bytes) -> list[str]:
    decoded = file_bytes.decode("utf-8-sig")
    lines = decoded.splitlines()
    if not lines:
        return []

    collected: list[str] = []
    csv_reader = csv.reader(io.StringIO(decoded))
    for row in csv_reader:
        for value in row:
            value = value.strip()
            if value:
                collected.append(value)
    return collected


def parse_recipients(text: str = "", uploaded_file=None) -> list[str]:
    candidates: list[str] = []
    if text:
        normalized = (
            text.replace("\r", "\n")
            .replace("\n", ",")
            .replace(";", ",")
            .replace("\t", ",")
            .replace(" ", ",")
        )
        for item in normalized.split(","):
            stripped = item.strip()
            if stripped:
                candidates.append(stripped)
    if uploaded_file:
        candidates.extend(_collect_csv_emails(uploaded_file.read()))

    cleaned: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        lowered = candidate.lower().strip()
        if not lowered or lowered in seen:
            continue
        try:
            validate_email(lowered)
        except ValidationError:
            continue
        seen.add(lowered)
        cleaned.append(lowered)
    return cleaned


@transaction.atomic
def create_batch(
    *,
    user,
    gmail_connection: GmailConnection,
    template: EmailTemplate | None,
    batch_name: str,
    subject: str,
    body: str,
    recipients: Iterable[str],
) -> EmailBatch:
    recipient_list = list(recipients)
    batch = EmailBatch.objects.create(
        user=user,
        gmail_connection=gmail_connection,
        template=template,
        name=batch_name or f"{timezone.now():%Y-%m-%d %H:%M} batch",
        subject=subject,
        body=body,
        recipient_count=len(recipient_list),
        status=EmailBatch.Status.QUEUED,
    )
    RecipientJob.objects.bulk_create(
        [RecipientJob(batch=batch, recipient_email=email) for email in recipient_list]
    )
    log_action(
        user,
        "batch.created",
        target=str(batch.pk),
        payload={
            "gmail_address": gmail_connection.gmail_address,
            "recipient_count": len(recipient_list),
            "template": template.name if template else "",
        },
    )
    return batch


def refresh_batch_status(batch: EmailBatch) -> EmailBatch.Status:
    sent = batch.jobs.filter(status=RecipientJob.Status.SENT).count()
    failed = batch.jobs.filter(status=RecipientJob.Status.FAILED).count()
    pending = batch.jobs.filter(
        status__in=[RecipientJob.Status.PENDING, RecipientJob.Status.SENDING]
    ).count()

    if pending > 0:
        status = EmailBatch.Status.PROCESSING if batch.started_at else EmailBatch.Status.QUEUED
        batch.completed_at = None
    elif sent > 0 and failed == 0:
        status = EmailBatch.Status.COMPLETED
    elif sent > 0 and failed > 0:
        status = EmailBatch.Status.PARTIAL
    else:
        status = EmailBatch.Status.FAILED

    batch.status = status
    if sent > 0 and not batch.started_at:
        batch.started_at = timezone.now()
    if pending == 0:
        batch.completed_at = timezone.now()
    batch.save(update_fields=["status", "started_at", "completed_at", "updated_at"])
    return status


def process_pending_jobs(*, limit: int = 20, batch_id: int | None = None, pause_seconds: float = 0.0) -> int:
    processed = 0
    queryset = RecipientJob.objects.select_related("batch", "batch__gmail_connection", "batch__user")
    queryset = queryset.filter(status=RecipientJob.Status.PENDING, batch__gmail_connection__is_active=True)
    if batch_id is not None:
        queryset = queryset.filter(batch_id=batch_id)
    queryset = queryset.order_by("created_at")[:limit]

    for job in queryset:
        batch = job.batch
        if batch.status in {EmailBatch.Status.COMPLETED, EmailBatch.Status.FAILED}:
            continue
        batch.status = EmailBatch.Status.PROCESSING
        if not batch.started_at:
            batch.started_at = timezone.now()
        batch.save(update_fields=["status", "started_at", "updated_at"])

        job.status = RecipientJob.Status.SENDING
        job.error_message = ""
        job.save(update_fields=["status", "error_message", "updated_at"])

        try:
            message_id = send_gmail_message(
                connection=batch.gmail_connection,
                recipient_email=job.recipient_email,
                subject=batch.subject,
                body=batch.body,
            )
        except Exception as exc:
            job.status = RecipientJob.Status.FAILED
            job.error_message = str(exc)
            job.sent_at = None
            job.save(update_fields=["status", "error_message", "sent_at", "updated_at"])
            log_action(
                batch.user,
                "recipient.failed",
                target=f"batch:{batch.pk}|{job.recipient_email}",
                payload={"error": str(exc)},
            )
        else:
            job.status = RecipientJob.Status.SENT
            job.provider_message_id = message_id
            job.sent_at = timezone.now()
            job.save(update_fields=["status", "provider_message_id", "sent_at", "updated_at"])
            log_action(
                batch.user,
                "recipient.sent",
                target=f"batch:{batch.pk}|{job.recipient_email}",
                payload={"message_id": message_id},
            )
        processed += 1
        refresh_batch_status(batch)
        if pause_seconds:
            time.sleep(pause_seconds)
    return processed
