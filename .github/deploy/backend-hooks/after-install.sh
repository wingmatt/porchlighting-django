#!/usr/bin/env bash
set -Eeuo pipefail
readonly APPCONFIG_ENV_FILE="/run/porchlight/production.env"

source "$(dirname "$0")/load-appconfig-env.sh"
load_appconfig_env
set -a
source "${APPCONFIG_ENV_FILE}"
set +a
cd /srv/porchlight/porchlight-django
uv sync --frozen
DJANGO_ENV=production uv run python manage.py migrate --noinput
DJANGO_ENV=production uv run python manage.py check --deploy