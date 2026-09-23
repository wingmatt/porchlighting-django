"""Firebase connection and database integration helpers."""
import logging
import os
from django.conf import settings

logger = logging.getLogger(__name__)

_firebase_app = None


def get_firebase_app():
    """Initialize or retrieve the singleton Firebase Admin App."""
    global _firebase_app
    if _firebase_app is not None:
        return _firebase_app

    try:
        import firebase_admin
        from firebase_admin import credentials

        if firebase_admin._apps:
            _firebase_app = firebase_admin.get_app()
            return _firebase_app

        cred_path = getattr(settings, 'FIREBASE_CREDENTIALS_PATH', None)
        database_url = getattr(settings, 'FIREBASE_DATABASE_URL', '')
        project_id = getattr(settings, 'FIREBASE_PROJECT_ID', 'porchlight-project')

        options = {}
        if database_url:
            options['databaseURL'] = database_url
        if project_id:
            options['projectId'] = project_id

        if cred_path and os.path.exists(cred_path):
            cred = credentials.Certificate(cred_path)
            _firebase_app = firebase_admin.initialize_app(cred, options)
            logger.info("Firebase initialized with service account certificate: %s", cred_path)
        else:
            # Fallback for dev / environment without explicit service account file
            try:
                cred = credentials.ApplicationDefault()
                _firebase_app = firebase_admin.initialize_app(cred, options)
                logger.info("Firebase initialized with ApplicationDefault credentials")
            except Exception:
                # Initialize unauthenticated / mock-ready app for dev
                _firebase_app = firebase_admin.initialize_app(options=options)
                logger.warning(
                    "Firebase initialized with default configuration (unauthenticated / development mode)."
                )

        return _firebase_app
    except Exception as e:
        logger.error("Failed to initialize Firebase app: %s", e)
        return None


def get_firestore_client():
    """Retrieve Firestore database client."""
    app = get_firebase_app()
    if not app:
        return None
    try:
        from firebase_admin import firestore
        return firestore.client(app=app)
    except Exception as e:
        logger.error("Failed to get Firestore client: %s", e)
        return None


def get_realtime_db_reference(path='/'):
    """Retrieve Realtime Database reference."""
    app = get_firebase_app()
    if not app:
        return None
    try:
        from firebase_admin import db
        return db.reference(path, app=app)
    except Exception as e:
        logger.error("Failed to get Realtime DB reference at %s: %s", path, e)
        return None


def sync_porchlight_to_firebase(porchlight_id: str, data: dict) -> bool:
    """Sync Porchlight real-time state to Firebase Firestore / Realtime DB."""
    try:
        client = get_firestore_client()
        if client:
            doc_ref = client.collection('porchlights').document(str(porchlight_id))
            doc_ref.set(data, merge=True)
            return True

        # Fallback to Realtime DB if firestore is unavailable
        db_ref = get_realtime_db_reference(f'porchlights/{porchlight_id}')
        if db_ref:
            db_ref.update(data)
            return True
    except Exception as e:
        logger.error("Failed to sync porchlight %s to Firebase: %s", porchlight_id, e)

    return False
