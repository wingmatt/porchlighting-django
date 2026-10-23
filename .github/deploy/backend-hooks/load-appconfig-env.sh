#!/usr/bin/env bash
set -Eeuo pipefail

readonly APPCONFIG_ENDPOINT="http://127.0.0.1:2772"
readonly APPCONFIG_APPLICATION="porchlight"
readonly APPCONFIG_ENVIRONMENT="production"
readonly APPCONFIG_CONFIGURATION_PROFILE="production"
readonly APPCONFIG_ENV_FILE="/run/porchlight/production.env"

load_appconfig_env() {
    local temporary_file
    temporary_file="$(mktemp "${APPCONFIG_ENV_FILE}.XXXXXX")"
    trap 'rm -f "${temporary_file}"' RETURN

    curl --fail --silent --show-error --retry 3 \
        "${APPCONFIG_ENDPOINT}/applications/${APPCONFIG_APPLICATION}/environments/${APPCONFIG_ENVIRONMENT}/configurations/${APPCONFIG_CONFIGURATION_PROFILE}" \
        --output "${temporary_file}"
    [[ -s "${temporary_file}" ]] || {
        printf 'error: AWS AppConfig returned an empty configuration\n' >&2
        exit 1
    }
    chmod 640 "${temporary_file}"
    mv -f "${temporary_file}" "${APPCONFIG_ENV_FILE}"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    load_appconfig_env
fi