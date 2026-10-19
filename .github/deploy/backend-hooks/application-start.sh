#!/usr/bin/env bash
set -Eeuo pipefail
sudo systemctl restart porchlight-django.service
sudo systemctl is-active --quiet porchlight-django.service