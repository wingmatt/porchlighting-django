### Architecture Overview & Migration Strategy

The goal is to migrate the **Porchlighting** application:
- **Backend**: Migrate from **Laravel 12 + Laravel Reverb / Echo** to **Django + Django REST Framework (DRF)** using **Firebase (Firestore / Realtime Database / Firebase Admin SDK)** for real-time synchronization.
- **Frontend**: Migrate from **Inertia.js + Vue 3** to a standalone **React + TypeScript + Tailwind CSS** application packaged with **CapacitorJS** for cross-platform mobile (iOS/Android) and web deployment.

---

### Backend Recreation: Django & Firebase

#### 1. Project Setup & Dependencies
Initialize a Django project with Django REST Framework, CORS headers, Sqids (for URL-safe invitation IDs matching the Laravel `sqids` package), and Firebase Admin SDK.

```bash
pip install django djangorestframework django-cors-headers firebase-admin sqids PyJWT
django-admin startproject config .
python manage.py startapp beacons
python manage.py startapp invitations
python manage.py startapp rsvps
python manage.py startapp accounts
```

In `config/settings.py`:
```python
INSTALLED_APPS = [
    # Django apps...
    'rest_framework',
    'rest_framework.authtoken',
    'corsheaders',
    'accounts',
    'beacons',
    'invitations',
    'rsvps',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    # Default Django middlewares...
    'accounts.middleware.GuestAuthMiddleware',
]

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
}
```

Initialize Firebase Admin in `config/firebase.py`:
```python
import firebase_admin
from firebase_admin import credentials, firestore

cred = credentials.Certificate("path/to/firebase-credentials.json")
firebase_app = firebase_admin.initialize_app(cred)
db = firestore.client()
```

---

#### 2. Models & Database Schema

##### `accounts/models.py`
```python
from django.contrib.auth.models import AbstractUser

class User(AbstractUser):
    # Matches Laravel user structure
    pass
```

##### `beacons/models.py`
```python
from django.db import models
from django.conf import settings
from datetime import timedelta
from django.utils import timezone

class Beacon(models.Model):
    name = models.CharField(max_length=255)
    type = models.CharField(max_length=100, default='default')
    active_duration = models.IntegerField(default=4)  # in hours
    active_until = models.DateTimeField(null=True, blank=True)
    location = models.TextField(null=True, blank=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='owned_beacons', on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def is_active(self):
        return self.active_until and self.active_until > timezone.now()
```

##### `invitations/models.py`
```python
from django.db import models
from django.conf import settings
from sqids import Sqids
from beacons.models import Beacon

sqids = Sqids(min_length=8)

class Invitation(models.Model):
    beacon = models.ForeignKey(Beacon, related_name='invitations', on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE)
    guest_token = models.CharField(max_length=255, null=True, blank=True)
    role_granted = models.CharField(max_length=50, default='view')  # owner, edit, share, view
    active_until = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def sqid(self) -> str:
        return sqids.encode([self.id])

    @classmethod
    def get_by_sqid(cls, sqid_str: str):
        numbers = sqids.decode(sqid_str)
        if not numbers:
            return None
        return cls.objects.filter(id=numbers[0]).first()
```

##### `invitations/permissions_models.py` (or `beacons/models.py`)
```python
class Permission(models.Model):
    beacon = models.ForeignKey(Beacon, related_name='permission_grants', on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, related_name='permissions', on_delete=models.CASCADE)
    guest_id = models.CharField(max_length=255, null=True, blank=True)
    role = models.CharField(max_length=50) # 'owner', 'edit', 'share', 'view'
    from_invitation = models.ForeignKey(Invitation, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
```

##### `rsvps/models.py`
```python
from django.db import models
from django.conf import settings
from beacons.models import Beacon

class Rsvp(models.Model):
    beacon = models.ForeignKey(Beacon, related_name='rsvps', on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE)
    guest_id = models.CharField(max_length=255, null=True, blank=True)
    type = models.CharField(max_length=20, null=True, blank=True) # 'yes', 'maybe'
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
```

---

#### 3. Guest & Authorization Middleware
Recreate `AuthorizeWithLocalStorageKey.php` via Django Middleware in `accounts/middleware.py`:

```python
class GuestAuthMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        guest_token = request.headers.get('X-Guest-Token')
        guest_name = request.headers.get('X-Guest-Name')
        request.guest_token = guest_token
        request.guest_name = guest_name
        return self.get_response(request)
```