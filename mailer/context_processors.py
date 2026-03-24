from django.conf import settings


def app_settings(_request):
    return {"app_name": settings.APP_NAME}
