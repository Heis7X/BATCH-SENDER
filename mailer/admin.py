from django.contrib import admin

from .models import AuditLog, EmailBatch, EmailTemplate, GmailConnection, RecipientJob


@admin.register(EmailTemplate)
class EmailTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "created_by", "is_shared", "is_active", "updated_at", "updated_by")
    list_filter = ("is_shared", "is_active", "created_by")
    search_fields = ("name", "subject", "body", "created_by__username", "created_by__email")


@admin.register(GmailConnection)
class GmailConnectionAdmin(admin.ModelAdmin):
    list_display = ("gmail_address", "user", "is_active", "updated_at", "last_used_at")
    list_filter = ("is_active", "user")
    search_fields = ("gmail_address", "display_name", "user__username", "user__email")
    readonly_fields = ("created_at", "updated_at", "last_used_at")


class RecipientJobInline(admin.TabularInline):
    model = RecipientJob
    extra = 0
    readonly_fields = ("recipient_email", "status", "provider_message_id", "error_message", "sent_at")
    can_delete = False


@admin.register(EmailBatch)
class EmailBatchAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "user",
        "gmail_connection",
        "template",
        "recipient_count",
        "status",
        "created_at",
    )
    list_filter = ("status", "gmail_connection", "user")
    search_fields = (
        "name",
        "subject",
        "body",
        "user__username",
        "user__email",
        "gmail_connection__gmail_address",
        "template__name",
    )
    inlines = [RecipientJobInline]


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "action", "target", "user")
    list_filter = ("action",)
    search_fields = ("action", "target", "user__username")
