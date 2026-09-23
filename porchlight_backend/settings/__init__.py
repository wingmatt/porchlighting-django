"""Modular settings package for Porchlight Django."""
import os
from .base import *  # noqa: F401, F403

env_name = os.getenv('DJANGO_ENV', 'development').lower()
if env_name == 'production':
    from .production import *  # noqa: F401, F403
else:
    from .development import *  # noqa: F401, F403
