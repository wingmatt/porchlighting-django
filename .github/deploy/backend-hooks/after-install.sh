#!/usr/bin/env bash
set -Eeuo pipefail
cd /srv/porchlight/porchlight-django
uv sync --frozen
DJANGO_ENV=production uv run python manage.py migrate --noinput
DJANGO_ENV=production uv run python manage.py check --deploy