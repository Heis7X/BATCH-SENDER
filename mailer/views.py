from __future__ import annotations

from django.conf import settings
from django.db.models import Q
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST
from django.contrib.auth import login
from .forms import SignUpForm

from .forms import ComposeBatchForm, EmailTemplateForm
from .models import EmailBatch, EmailTemplate, GmailConnection
from .services import (
    MailerConfigError,
    build_google_flow,
    create_batch,
    credentials_to_dict,
    encrypt_json,
    fetch_google_profile,
    log_action,
    parse_recipients,
    process_pending_jobs,
)



def is_admin(user) -> bool:
    return user.is_authenticated and user.is_staff


@login_required
@require_GET
def dashboard(request: HttpRequest) -> HttpResponse:
    recent_batches = EmailBatch.objects.select_related("gmail_connection", "template")
    if not request.user.is_staff:
        recent_batches = recent_batches.filter(user=request.user)
    recent_batches = recent_batches[:5]

    stats = {
        "template_count": EmailTemplate.objects.filter(is_active=True).count(),
        "connection_count": GmailConnection.objects.filter(user=request.user, is_active=True).count(),
        "queued_batches": EmailBatch.objects.filter(user=request.user, status=EmailBatch.Status.QUEUED).count(),
        "completed_batches": EmailBatch.objects.filter(user=request.user, status=EmailBatch.Status.COMPLETED).count(),
    }

    return render(
        request,
        "mailer/dashboard.html",
        {
            "stats": stats,
            "recent_batches": recent_batches,
            "app_name": settings.APP_NAME,
        },
    )


@login_required
@user_passes_test(is_admin)
def template_list(request: HttpRequest) -> HttpResponse:
    templates = EmailTemplate.objects.all().order_by("name")
    return render(request, "mailer/templates_list.html", {"templates": templates})


@login_required
@user_passes_test(is_admin)
def template_create(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = EmailTemplateForm(request.POST)
        if form.is_valid():
            template = form.save(commit=False)
            template.created_by = request.user
            template.is_shared = True
            template.updated_by = request.user
            template.save()
            log_action(request.user, "template.created", str(template.pk), {"name": template.name})
            messages.success(request, "Template created.")
            return redirect("template_list")
    else:
        form = EmailTemplateForm()
    return render(request, "mailer/template_form.html", {"form": form, "title": "Create template"})


@login_required
@user_passes_test(is_admin)
def template_update(request: HttpRequest, pk: int) -> HttpResponse:
    template = get_object_or_404(EmailTemplate, pk=pk)
    if request.method == "POST":
        form = EmailTemplateForm(request.POST, instance=template)
        if form.is_valid():
            template = form.save(commit=False)
            template.updated_by = request.user
            template.save()
            log_action(request.user, "template.updated", str(template.pk), {"name": template.name})
            messages.success(request, "Template updated.")
            return redirect("template_list")
    else:
        form = EmailTemplateForm(instance=template)
    return render(request, "mailer/template_form.html", {"form": form, "title": f"Edit {template.name}"})


@login_required
@user_passes_test(is_admin)
def template_delete(request: HttpRequest, pk: int) -> HttpResponse:
    template = get_object_or_404(EmailTemplate, pk=pk)
    if request.method == "POST":
        name = template.name
        template.delete()
        log_action(request.user, "template.deleted", str(pk), {"name": name})
        messages.success(request, "Template deleted.")
        return redirect("template_list")
    return render(request, "mailer/template_delete.html", {"template": template})


@login_required
def connection_list(request: HttpRequest) -> HttpResponse:
    connections = GmailConnection.objects.filter(user=request.user).order_by("gmail_address")
    return render(request, "mailer/connections.html", {"connections": connections})

import secrets

@login_required
@require_GET
def gmail_connect(request: HttpRequest) -> HttpResponse:
    try:
        code_verifier = secrets.token_urlsafe(64)
        flow = build_google_flow(code_verifier=code_verifier)
        authorization_url, state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )
    except MailerConfigError as exc:
        messages.error(request, str(exc))
        return redirect("connection_list")

    request.session["gmail_oauth_state"] = state
    request.session["gmail_oauth_code_verifier"] = code_verifier
    return redirect(authorization_url)


@login_required
@require_GET
def gmail_callback(request: HttpRequest) -> HttpResponse:
    try:
        state = request.session.get("gmail_oauth_state")
        code_verifier = request.session.get("gmail_oauth_code_verifier")

        if not state or request.GET.get("state") != state:
            messages.error(request, "OAuth state mismatch. Please reconnect.")
            return redirect("connection_list")

        if not code_verifier:
            messages.error(request, "Missing code verifier. Please reconnect.")
            return redirect("connection_list")

        flow = build_google_flow(state=state, code_verifier=code_verifier)
        flow.fetch_token(authorization_response=request.build_absolute_uri())

        credentials = flow.credentials
        profile = fetch_google_profile(credentials)

        gmail_address = profile.get("email")

        connection, created = GmailConnection.objects.update_or_create(
            user=request.user,
            gmail_address=gmail_address,
            defaults={
                "display_name": profile.get("name", ""),
                "encrypted_credentials": encrypt_json(credentials_to_dict(credentials)),
                "is_active": True,
                "last_error": "",
            },
        )

        request.session.pop("gmail_oauth_state", None)
        request.session.pop("gmail_oauth_code_verifier", None)

        messages.success(request, f"Gmail connected: {gmail_address}")
        return redirect("connection_list")

    except Exception as exc:
        messages.error(request, f"Gmail error: {exc}")
        return redirect("connection_list")


def signup(request):
    if request.user.is_authenticated:
        return redirect("connection_list")

    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("connection_list")
    else:
        form = SignUpForm()

    return render(request, "registration/signup.html", {"form": form})


@login_required
@require_POST
def connection_toggle(request: HttpRequest, pk: int) -> HttpResponse:
    connection = get_object_or_404(GmailConnection, pk=pk, user=request.user)
    connection.is_active = not connection.is_active
    connection.save(update_fields=["is_active", "updated_at"])
    log_action(
        request.user,
        "gmail.toggled",
        str(connection.pk),
        {"gmail_address": connection.gmail_address, "is_active": connection.is_active},
    )
    messages.success(
        request,
        f"{connection.gmail_address} is now {'active' if connection.is_active else 'inactive'}.",
    )
    return redirect("connection_list")


@login_required
def compose_batch(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = ComposeBatchForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            template = form.cleaned_data["template"]
            subject = form.cleaned_data["subject"] or (template.subject if template else "")
            body = form.cleaned_data["body"] or (template.body if template else "")
            recipients = parse_recipients(
                form.cleaned_data.get("recipients_text", ""),
                form.cleaned_data.get("recipients_file"),
            )

            if not subject.strip():
                form.add_error("subject", "Add a subject or select a template that has one.")
            if not body.strip():
                form.add_error("body", "Add email body content or select a template that has it.")
            if not recipients:
                form.add_error("recipients_text", "Add at least one valid email recipient.")
            if len(recipients) > settings.EMAIL_BATCH_MAX_RECIPIENTS:
                form.add_error(
                    "recipients_text",
                    f"You can send to up to {settings.EMAIL_BATCH_MAX_RECIPIENTS} recipients at once.",
                )

            if not form.errors:
                batch = create_batch(
                    user=request.user,
                    gmail_connection=form.cleaned_data["gmail_connection"],
                    template=template,
                    batch_name=form.cleaned_data["batch_name"],
                    subject=subject,
                    body=body,
                    recipients=recipients,
                )
                messages.success(
                    request,
                    f"Batch queued for {len(recipients)} recipients. Start the worker or use Process Now to send.",
                )
                return redirect("batch_detail", pk=batch.pk)
    else:
        form = ComposeBatchForm(user=request.user)

    templates = list(
    EmailTemplate.objects.filter(
        Q(is_shared=True) | Q(created_by=request.user),
        is_active=True
    ).values("id", "name", "subject", "body")
)


@login_required
def batch_list(request: HttpRequest) -> HttpResponse:
    batches = EmailBatch.objects.select_related("gmail_connection", "template", "user")
    if not request.user.is_staff:
        batches = batches.filter(user=request.user)
    return render(request, "mailer/batches.html", {"batches": batches[:100]})


@login_required
def batch_detail(request: HttpRequest, pk: int) -> HttpResponse:
    batch = get_object_or_404(EmailBatch.objects.select_related("gmail_connection", "template", "user"), pk=pk)
    if not request.user.is_staff and batch.user != request.user:
        messages.error(request, "You do not have access to that batch.")
        return redirect("batch_list")
    jobs = batch.jobs.all()
    return render(request, "mailer/batch_detail.html", {"batch": batch, "jobs": jobs})


@login_required
@require_POST
def process_batch_now(request: HttpRequest, pk: int) -> HttpResponse:
    batch = get_object_or_404(EmailBatch, pk=pk)
    if not request.user.is_staff and batch.user != request.user:
        messages.error(request, "You do not have permission to process this batch.")
        return redirect("batch_list")

    processed = process_pending_jobs(limit=25, batch_id=batch.pk, pause_seconds=0.0)
    if processed:
        messages.success(request, f"Processed {processed} queued recipient(s) for this batch.")
    else:
        messages.info(request, "No queued recipients were available for this batch.")
    return redirect("batch_detail", pk=batch.pk)
