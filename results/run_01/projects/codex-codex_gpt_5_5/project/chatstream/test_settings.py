import os
import secrets

os.environ.setdefault("DJANGO_SECRET_KEY", secrets.token_urlsafe(64))
os.environ.setdefault("DJANGO_ALLOWED_HOSTS", "testserver,localhost,127.0.0.1,[::1]")
os.environ.setdefault("DJANGO_DEBUG", "False")

from chatstream.settings import *  # noqa: F403
