#!/bin/bash
set -e

python manage.py collectstatic --noinput --verbosity 0
exec daphne -b 0.0.0.0 -p 8000 config.asgi:application
