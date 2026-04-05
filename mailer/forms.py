from __future__ import annotations

from django import forms

from .models import SMTPConnection

from django.db.models import Q
from .models import EmailTemplate, GmailConnection


class EmailTemplateForm(forms.ModelForm):
    class Meta:
        model = EmailTemplate
        fields = ["name", "subject", "body", "is_active"]
        widgets = {
            "body": forms.Textarea(attrs={"rows": 12}),
        }


class ComposeBatchForm(forms.Form):
    batch_name = forms.CharField(max_length=150, required=False)
    template = forms.ModelChoiceField(
        queryset=EmailTemplate.objects.none(),
        required=False,
        empty_label="Select a saved template",
    )
    gmail_connection = forms.ModelChoiceField(
        queryset=GmailConnection.objects.none(),
        required=True,
        empty_label="Select a connected Gmail account",
    )
    subject = forms.CharField(max_length=255, required=False)
    body = forms.CharField(widget=forms.Textarea(attrs={"rows": 12}), required=False)
    recipients_text = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 10,
                "placeholder": "Paste up to 100 emails, separated by commas, spaces, or new lines.",
            }
        ),
        help_text="You can paste emails separated by commas, spaces, or new lines.",
    )
    recipients_file = forms.FileField(
        required=False,
        help_text="Optional CSV or TXT file with one email per line or a column that contains email addresses.",
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)

        if user is not None:
            self.fields["template"].queryset = EmailTemplate.objects.filter(
                Q(is_shared=True) | Q(created_by=user),
                is_active=True,
            ).order_by("name")

            self.fields["gmail_connection"].queryset = GmailConnection.objects.filter(
                user=user,
                is_active=True,
            ).order_by("gmail_address")

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user")
        super().__init__(*args, **kwargs)
        self.fields["template"].queryset = EmailTemplate.objects.filter(is_active=True).order_by("name")
        self.fields["gmail_connection"].queryset = GmailConnection.objects.filter(
            user=user, is_active=True
        ).order_by("gmail_address")


class SMTPConnectionForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput(render_value=True))

    class Meta:
        model = SMTPConnection
        fields = [
            "name",
            "from_email",
            "display_name",
            "reply_to_email",
            "smtp_host",
            "smtp_port",
            "username",
            "password",
            "use_tls",
            "use_ssl",
            "is_active",
        ]

from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User


class SignUpForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("Email already exists")
        return email