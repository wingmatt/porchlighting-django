# Porchlight Django Backend

Porchlight backend built with Django, Django REST Framework (DRF), and Firebase Admin SDK.

## Prerequisites

- **Python**: Version `>= 3.13`
- **uv**: Fast Python package and environment manager ([installation guide](https://docs.astral.sh/uv/getting-started/installation/))
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

# Firebase Settings (Optional for local testing / features not using Firebase)
FIREBASE_CREDENTIALS_PATH=path/to/firebase-service-account.json
FIREBASE_DATABASE_URL=https://<your-project-id>.firebaseio.com
FIREBASE_PROJECT_ID=<your-firebase-project-id>
FIREBASE_STORAGE_BUCKET=<your-storage-bucket>.appspot.com
```

> **Note**: Missing Firebase credentials will be handled gracefully during local development and automated testing if Firebase features are not actively invoked.

### 4. Apply Database Migrations

Initialize the SQLite database with the existing migrations:

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
