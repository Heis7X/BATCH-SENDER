from django.contrib import admin

from .models import AuditLog, EmailBatch, EmailTemplate, GmailConnection, RecipientJob


@admin.register(EmailTemplate)
class EmailTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "updated_at", "updated_by")
    list_filter = ("is_active",)
    search_fields = ("name", "subject", "body")


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
        "recipient_count",
        "status",
        "created_at",
    )
    list_filter = ("status", "gmail_connection", "user")
    search_fields = ("name", "subject", "body", "user__username", "gmail_connection__gmail_address")
    inlines = [RecipientJobInline]


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "action", "target", "user")
    list_filter = ("action",)
    search_fields = ("action", "target", "user__username")
