#!/usr/bin/env bash
set -Eeuo pipefail
readonly ENV_FILE="/run/porchlight/production.env"

python3 "$(dirname "$0")/load-aws-env.py" --write-env-file "${ENV_FILE}"
cd /srv/porchlight/porchlight-django
uv sync --frozen
python3 "$(dirname "$0")/load-aws-env.py" --migration uv run python manage.py migrate --noinput
python3 "$(dirname "$0")/load-aws-env.py" -- uv run python manage.py check --deploy