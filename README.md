# Porchlight Django Backend

Porchlight backend built with Django 6.1+, Django REST Framework (DRF), PostgreSQL / PostGIS, and Firebase Admin SDK.

## Prerequisites

- **Python**: Version `>= 3.13`
- **uv**: Fast Python package and environment manager ([installation guide](https://docs.astral.sh/uv/getting-started/installation/))
- **PostgreSQL / PostGIS** (Production / optional local PostgreSQL): PostgreSQL database with PostGIS spatial extension enabled
- **Git**

---

## Getting Started (Local Development Setup)

Follow the steps below to initialize and run the local development environment:

### 1. Clone the Repository

```bash
git clone <repository_url>
cd porchlight-django
```

### 2. Install Dependencies

Using `uv`, sync and install the required dependencies and virtual environment:

```bash
uv sync
```

### 3. Configure Environment Variables

Create a `.env` file in the project root directory:

```env
# Django Settings
DJANGO_SECRET_KEY=your-local-secret-key
DEBUG=True

# Database Configuration
# Local development defaults to SQLite. To use PostgreSQL / PostGIS locally or in production:
# DATABASE_URL=postgis://postgres:postgres@localhost:5432/porchlight_db
# Or individual variables:
# POSTGRES_DB=porchlight_db
# POSTGRES_USER=postgres
# POSTGRES_PASSWORD=postgres
# POSTGRES_HOST=localhost
# POSTGRES_PORT=5432
# USE_POSTGRES=True

# Firebase Settings (Used to broadcast database updates in real-time)
FIREBASE_CREDENTIALS_PATH=path/to/firebase-service-account.json
FIREBASE_DATABASE_URL=https://<your-project-id>.firebaseio.com
FIREBASE_PROJECT_ID=<your-firebase-project-id>
FIREBASE_STORAGE_BUCKET=<your-storage-bucket>.appspot.com

# Local email (MailPit SMTP; web inbox at http://localhost:8025)
EMAIL_HOST=127.0.0.1
EMAIL_PORT=1025
DEFAULT_FROM_EMAIL=no-reply@porchlight.local
# Optional override for the link included in confirmation emails
# EMAIL_CONFIRMATION_URL=http://127.0.0.1:8000/api/auth/confirm-email/{uid}/{token}/
```

> **Note**: Missing Firebase credentials will be handled gracefully during local development and automated testing if Firebase features are not actively invoked.

### Local email with MailPit

Development settings send signup confirmation email through MailPit. Start MailPit
with Docker, then open `http://localhost:8025` to inspect messages:

```bash
docker run --rm -p 1025:1025 -p 8025:8025 axllent/mailpit
```

New accounts remain inactive until the confirmation link in the MailPit message is opened.

### Production email with SendGrid

Production settings use SendGrid SMTP. Set the following environment variables in the
deployment environment; never commit the API key:

```env
SENDGRID_API_KEY=your-sendgrid-api-key
DEFAULT_FROM_EMAIL=no-reply@your-domain.example
EMAIL_CONFIRMATION_URL=https://api.your-domain.example/api/auth/confirm-email/{uid}/{token}/
```

The SMTP host is `smtp.sendgrid.net`, port `587`, with TLS enabled and username `apikey`.

### 4. Apply Database Migrations

Initialize the database (SQLite for local dev by default, or PostgreSQL/PostGIS in production) with the migrations:

```bash
uv run python manage.py migrate
```

### 5. Create a Superuser (Optional)

Create an admin account to access the Django admin panel:

```bash
uv run python manage.py createsuperuser
```

### 6. Start the Development Server

Start the local Django development server:

```bash
uv run python manage.py runserver
```

The API and admin dashboard will be available at:
- Base URL: `http://127.0.0.1:8000/`
- Admin Panel: `http://127.0.0.1:8000/admin/`

---

## Running Tests

Run the test suite using `manage.py`:

```bash
# Run all tests
uv run python manage.py test

# Run tests for specific applications
uv run python manage.py test apps.accounts
uv run python manage.py test apps.porchlights
uv run python manage.py test apps.core
```

---

## Common Development Commands

### Dependency Management with `uv`

- **Add a new package**:
  ```bash
  uv add <package_name>
  ```
- **Add a development package**:
  ```bash
  uv add --dev <package_name>
  ```
- **Remove a package**:
  ```bash
  uv remove <package_name>
  ```
- **Update lockfile**:
  ```bash
  uv lock
  ```

### Database & Migrations

- **Create new migrations after model changes**:
  ```bash
  uv run python manage.py makemigrations
  ```
- **Apply migrations**:
  ```bash
  uv run python manage.py migrate
  ```

---

## Architecture & Data Flow

1. **Database as Single Source of Truth**:
   - Production uses **PostgreSQL with PostGIS** (`django.contrib.gis.db.backends.postgis`).
   - Development defaults to SQLite for zero-setup execution, with optional local PostgreSQL/PostGIS.
   - All state mutations (accounts, porchlights, invitations, logs) are transacted and validated through Django models in PostgreSQL.

2. **Geocoordinates & Location Field**:
   - The `Porchlight.location` model field stores structured geocoordinates (e.g. `{latitude, longitude}`, `[lng, lat]`, or GeoJSON `Point`).
   - The model and serializers expose normalized `coordinates` (`[longitude, latitude]`) for client consumption and map rendering.

3. **Firebase Real-Time Broadcast**:
   - Firebase is used exclusively as a real-time broadcast and event delivery bus.
   - When models are saved or updated, Django signals (`post_save`) trigger Firebase Admin SDK helpers to mirror state to Firestore / Realtime Database, allowing connected clients to receive instant updates without polling.

---

## Project Structure

```text
porchlight-django/
├── apps/
│   ├── accounts/      # Custom user model (email-based auth), serializers, auth views
│   ├── core/          # Core utilities and Firebase integration helpers
│   └── porchlights/   # Porchlight domain models, views, permissions, serializers
├── porchlight_backend/
│   ├── settings/      # Modular settings (base.py, development.py, production.py)
│   ├── urls.py        # Root URL routing
│   ├── asgi.py        # ASGI entry point
│   └── wsgi.py        # WSGI entry point
├── manage.py          # Django management script
├── pyproject.toml     # Project metadata and dependencies
└── uv.lock            # uv dependency lockfile
```
