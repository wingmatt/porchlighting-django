# Project Guidelines for Porchlight Django

This document provides instructions and guidelines for working efficiently with the `porchlight-django` repository using `uv` and Django.

---

## 1. Project Overview & Architecture

- **Framework**: Django (>=6.1.1) with Django REST Framework (DRF) and Firebase Admin SDK.
- **Python Version**: Python >= 3.13.
- **Package & Environment Manager**: `uv`.
- **Project Structure**:
  - `apps/`: Modular Django applications.
    - `apps.accounts`: Custom user model (email-based auth), serializers, auth views.
    - `apps.porchlights`: Porchlight domain models, views, permissions, serializers.
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
    - `FIREBASE_CREDENTIALS_PATH`: Path to Firebase service account JSON credentials.
    - `FIREBASE_DATABASE_URL`: Firebase Realtime Database URL.
    - `FIREBASE_PROJECT_ID`: Firebase project ID.
    - `FIREBASE_STORAGE_BUCKET`: Firebase Storage bucket.

---

## 5. Coding & App Conventions

- **App Modules**: All domain apps must reside in `apps/<app_name>` and be registered in `INSTALLED_APPS` as `'apps.<app_name>'`.
- **Imports**: Use absolute imports referencing `apps.<app_name>...` or `porchlight_backend...`.
- **Custom User Model**: The project uses `AUTH_USER_MODEL = 'accounts.User'`. Always reference the user model via `django.contrib.auth.get_user_model()` or `settings.AUTH_USER_MODEL`.
- **Firebase Services**: Firebase initialization and helpers are centralized in `apps.core.firebase`. Ensure Firebase service calls handle missing credentials gracefully during local development and testing.
- **Security**: Never commit secrets, `.env` files, or Firebase service account keys to version control (configured in `.gitignore`).
