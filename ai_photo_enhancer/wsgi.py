"""WSGI entrypoint."""
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ai_photo_enhancer.settings")

application = get_wsgi_application()

if os.environ.get("VERCEL"):
    # Vercel's filesystem is read-only except /tmp, which is wiped on cold
    # starts — so build the schema there on import.
    from django.core.management import call_command

    call_command("migrate", "--no-input", verbosity=0, run_syncdb=True)
