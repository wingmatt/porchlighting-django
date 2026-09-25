# Project Guidelines for Porchlight Django

This document provides instructions and guidelines for working efficiently with the `porchlight-django` repository using `uv` and Django.

---

## 1. Project Overview & Architecture

- **Framework**: Django (>=6.1.1) with Django REST Framework (DRF) and Firebase Admin SDK.
- **Python Version**: Python >= 3.13.
- **Package & Environment Manager**: `uv`.
- **Database Architecture**:
  - **Production**: PostgreSQL with PostGIS extension (`django.contrib.gis.db.backends.postgis` via `psycopg[binary]`). PostgreSQL is the single source of truth for all application data.
  - **Development / Local**: Defaults to SQLite (`sqlite3`) for zero-configuration local development, with optional local PostgreSQL/PostGIS support when `USE_POSTGRES` or `DATABASE_URL` is configured.
  - **Firebase Role**: Firebase is used strictly as a real-time broadcast/event bus to stream database mutations and beacon state updates to connected clients. All persistent data originates in and is validated by PostgreSQL.
- **Project Structure**:
  - `apps/`: Modular Django applications.
    - `apps.accounts`: Custom user model (email-based auth), serializers, auth views.
    - `apps.porchlights`: Porchlight domain models, geocoordinates handling, views, permissions, serializers.
    - `apps.core`: Core utilities and Firebase integration helpers.
  - `porchlight_backend/`: Django project configuration.
    - `settings/`: Modular settings (`base.py`, `development.py`, `production.py`).
    - `urls.py`: Root URL routing.
    - `asgi.py` / `wsgi.py`: ASGI/WSGI entry points.
  - `manage.py`: Django management script (defaults to `porchlight_backend.settings.development`).

---

## 2. Dependency Management with `uv`

Always use `uv` for managing dependencies and running commands within the project environment.

### Basic Commands
- **Run Django commands**:
  ```powershell
  uv run python manage.py <command>
  ```
- **Sync dependencies / install environment**:
  ```powershell
  uv sync
  ```
- **Add a dependency**:
  ```powershell
  uv add <package_name>
  ```
- **Add a development dependency**:
  ```powershell
  uv add --dev <package_name>
  ```
- **Remove a dependency**:
  ```powershell
  uv remove <package_name>
  ```
- **Update lockfile**:
  ```powershell
  uv lock
  ```

---

## 3. Django Development Workflow

### Database & Migrations
- **Make migrations**:
  ```powershell
  uv run python manage.py makemigrations
  ```
- **Apply migrations**:
  ```powershell
  uv run python manage.py migrate
  ```

### Running the Development Server
```powershell
uv run python manage.py runserver
```

### Running Tests
- **Run all tests**:
  ```powershell
  uv run python manage.py test
  ```
- **Run tests for a specific app**:
  ```powershell
  uv run python manage.py test apps.accounts
  uv run python manage.py test apps.porchlights
  uv run python manage.py test apps.core
  ```

---

## 4. Settings & Environment Configuration

- **Settings Modules**:
  - `porchlight_backend.settings.development` (default in `manage.py`)
  - `porchlight_backend.settings.production`
  - `porchlight_backend.settings.base`
- **Specifying Settings**:
  To run commands with a specific settings module, pass `--settings`:
  ```powershell
  uv run python manage.py test --settings=porchlight_backend.settings.development
  ```
- **Environment Variables**:
  - Defined in `.env` (loaded automatically by `python-dotenv` in `base.py`).
  - Key environment variables:
    - `DJANGO_SECRET_KEY`: Django secret key.
    - `DEBUG`: Boolean debug flag.
    - `DATABASE_URL`: PostgreSQL connection URL (e.g., `postgis://user:pass@host:5432/dbname` or `postgres://...`).
    - `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT`: Individual PostgreSQL connection parameters.
    - `USE_POSTGRES`: Explicit flag to enable PostgreSQL/PostGIS in development.
    - `FIREBASE_CREDENTIALS_PATH`: Path to Firebase service account JSON credentials.
    - `FIREBASE_DATABASE_URL`: Firebase Realtime Database URL.
    - `FIREBASE_PROJECT_ID`: Firebase project ID.
    - `FIREBASE_STORAGE_BUCKET`: Firebase Storage bucket.
    - `DEFAULT_FROM_EMAIL`: Sender address for account confirmation emails.
    - `EMAIL_CONFIRMATION_URL`: URL template containing `{uid}` and `{token}` for confirmation links.
  - Development email is delivered to MailPit over SMTP at `127.0.0.1:1025` and viewed at `http://localhost:8025`.
  - Production email uses SendGrid SMTP (`smtp.sendgrid.net:587`) with `SENDGRID_API_KEY`; never commit this secret.
  - `SENTRY_DSN`, `SENTRY_ENVIRONMENT`, `SENTRY_TRACES_SAMPLE_RATE`, and `SENTRY_PROFILES_SAMPLE_RATE` configure Sentry errors, traces, and profiling.
  - `NEW_RELIC_ENABLED`, `NEW_RELIC_LICENSE_KEY`, and `NEW_RELIC_APP_NAME` configure New Relic APM; never commit monitoring credentials.
  - Sentry and New Relic are initialized from the WSGI/ASGI entry points only when configured, so development and tests remain credential-free.

---

## 5. Coding & App Conventions

- **App Modules**: All domain apps must reside in `apps/<app_name>` and be registered in `INSTALLED_APPS` as `'apps.<app_name>'`.
- **Imports**: Use absolute imports referencing `apps.<app_name>...` or `porchlight_backend...`.
- **Custom User Model**: The project uses `AUTH_USER_MODEL = 'accounts.User'`. Always reference the user model via `django.contrib.auth.get_user_model()` or `settings.AUTH_USER_MODEL`.
- **Location & Geocoordinates**: The `Porchlight.location` model field stores geocoordinates and supports JSON/GeoJSON coordinates (e.g. `{latitude, longitude}`, `{lat, lng}`, `[lng, lat]`, or GeoJSON Point). Model property `coordinates` and serializer fields normalize geocoordinates for API responses.
- **Firebase Broadcast Service**: Firebase synchronization (`apps.core.firebase` and `apps.porchlights.signals`) operates strictly as an outbound event broadcast mechanism triggered on database transactions (`post_save` / `on_commit`). PostgreSQL remains the single source of truth. Ensure Firebase service calls handle missing credentials gracefully during local development and testing.
- **Security**: Never commit secrets, `.env` files, or Firebase service account keys to version control (configured in `.gitignore`).
