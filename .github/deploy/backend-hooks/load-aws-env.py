#!/usr/bin/env python3
"""Load production configuration from Parameter Store."""

import json
import os
import subprocess
import sys
import tempfile
from urllib.parse import quote, urlsplit, urlunsplit
from pathlib import Path


PARAMETER_PATH = "/porchlight/production/"
FIREBASE_CREDENTIALS_PARAMETER = "FIREBASE_SERVICE_ACCOUNT_JSON"
FIREBASE_CREDENTIALS_PATH = "/run/porchlight/firebase-service-account.json"


def aws_json(*arguments):
    result = subprocess.run(
        ["aws", *arguments, "--output", "json"],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def fetch_environment():
    response = aws_json(
        "ssm", "get-parameters-by-path", "--path", PARAMETER_PATH,
        "--recursive", "--with-decryption",
    )
    parameters = {
        item["Name"].removeprefix(PARAMETER_PATH): item["Value"]
        for item in response.get("Parameters", [])
    }
    firebase_credentials = parameters.pop(FIREBASE_CREDENTIALS_PARAMETER, None)
    environment = parameters
    if not environment or any("/" in key for key in environment):
        raise ValueError("Parameter Store returned no values or an invalid parameter name")
    if not environment.get("DATABASE_URL"):
        raise ValueError("Parameter Store must contain a non-empty DATABASE_URL")
    if not firebase_credentials:
        raise ValueError(
            "Parameter Store must contain FIREBASE_SERVICE_ACCOUNT_JSON"
        )
    environment["DJANGO_ENV"] = "production"
    if firebase_credentials:
        try:
            credentials = json.loads(firebase_credentials)
        except json.JSONDecodeError as error:
            raise ValueError("Firebase service-account parameter is not valid JSON") from error
        if not isinstance(credentials, dict) or credentials.get("type") != "service_account":
            raise ValueError("Firebase service-account parameter must be a service-account JSON object")
        environment["FIREBASE_CREDENTIALS_PATH"] = FIREBASE_CREDENTIALS_PATH
    return environment, firebase_credentials


def migration_environment(environment):
    username = environment.get("DB_MIGRATION_USER")
    password = environment.get("DB_MIGRATION_PASSWORD")
    if not username or not password:
        raise ValueError("DB_MIGRATION_USER and DB_MIGRATION_PASSWORD are required for migrations")
    parsed = urlsplit(environment["DATABASE_URL"])
    if not parsed.hostname:
        raise ValueError("DATABASE_URL must contain a database host")
    host = parsed.hostname
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    if parsed.port:
        host = f"{host}:{parsed.port}"
    netloc = f"{quote(username, safe='')}:{quote(password, safe='')}@{host}"
    environment["DATABASE_URL"] = urlunsplit(parsed._replace(netloc=netloc))
    return environment


def write_environment_file(environment, destination):
    lines = []
    for key, value in environment.items():
        if not key.replace("_", "").isalnum() or not key[0].isalpha():
            raise ValueError(f"Invalid environment variable name: {key!r}")
        if "\n" in value or "\r" in value:
            raise ValueError(f"Environment value for {key} must be one line")
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'{key}="{escaped}"')
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write("\n".join(lines) + "\n")
        os.chmod(temporary_name, 0o640)
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def write_firebase_credentials(credentials_json):
    path = Path(FIREBASE_CREDENTIALS_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(credentials_json)
            if not credentials_json.endswith("\n"):
                output.write("\n")
        os.chmod(temporary_name, 0o640)
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def main():
    try:
        environment, firebase_credentials = fetch_environment()
        if len(sys.argv) == 3 and sys.argv[1] == "--write-env-file":
            write_environment_file(environment, sys.argv[2])
            write_firebase_credentials(firebase_credentials)
        elif len(sys.argv) >= 3 and sys.argv[1] in ("--", "--migration"):
            if sys.argv[1] == "--migration":
                environment = migration_environment(environment)
            os.execvpe(sys.argv[2], sys.argv[2:], {**os.environ, **environment})
        else:
            raise ValueError("usage: load-aws-env.py --write-env-file PATH | -- COMMAND [ARGS...]")
    except (OSError, subprocess.CalledProcessError, ValueError, json.JSONDecodeError) as error:
        print(f"error: unable to load production AWS configuration: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())