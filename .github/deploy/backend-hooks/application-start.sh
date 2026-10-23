#!/usr/bin/env bash
set -Eeuo pipefail

source "$(dirname "$0")/load-appconfig-env.sh"
load_appconfig_env
sudo systemctl restart porchlight-django.service
sudo systemctl is-active --quiet porchlight-django.service