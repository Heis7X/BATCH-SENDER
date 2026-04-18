from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("templates/", views.template_list, name="template_list"),
    path("templates/new/", views.template_create, name="template_create"),
    path("templates/<int:pk>/edit/", views.template_update, name="template_update"),
    path("templates/<int:pk>/delete/", views.template_delete, name="template_delete"),
    path("gmail/", views.connection_list, name="connection_list"),
    path("gmail/connect/", views.gmail_connect, name="gmail_connect"),
    path("gmail/callback/", views.gmail_callback, name="gmail_callback"),
    path("gmail/<int:pk>/toggle/", views.connection_toggle, name="connection_toggle"),
    path("compose/", views.compose_batch, name="compose_batch"),
    path("batches/", views.batch_list, name="batch_list"),
    path("templates/create/", views.user_template_create, name="user_template_create"),
    path("batches/<int:pk>/", views.batch_detail, name="batch_detail"),
    path("batches/<int:pk>/process/", views.process_batch_now, name="process_batch_now"),
    path("signup/", views.signup, name="signup"),
    path("smtp/", views.smtp_connection_list, name="smtp_connection_list"),
    path("smtp/create/", views.smtp_connection_create, name="smtp_connection_create"),
    path("smtp/<int:pk>/toggle/", views.smtp_connection_toggle, name="smtp_connection_toggle"),
]