"""
WSGI config for BITE.co Manejador de Reportes.

Es lo que Gunicorn importa para servir la app: `gunicorn bite.wsgi:application`
"""
import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "bite.settings")
application = get_wsgi_application()
