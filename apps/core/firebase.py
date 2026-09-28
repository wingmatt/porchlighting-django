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
        project_id = getattr(settings, 'FIREBASE_PROJECT_ID', '')

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


def delete_porchlight_from_firebase(porchlight_id: str) -> bool:
    """Delete Porchlight document / node from Firebase Firestore / Realtime DB."""
    try:
        client = get_firestore_client()
        if client:
            client.collection('porchlights').document(str(porchlight_id)).delete()
            return True

        db_ref = get_realtime_db_reference(f'porchlights/{porchlight_id}')
        if db_ref:
            db_ref.delete()
            return True
    except Exception as e:
        logger.error("Failed to delete porchlight %s from Firebase: %s", porchlight_id, e)

    return False


def create_firebase_custom_token(uid: str, additional_claims: dict | None = None) -> str | None:
    """Mint a Firebase Custom Auth Token for a given user/guest UID and optional claims."""
    app = get_firebase_app()
    if not app:
        return None
    try:
        from firebase_admin import auth
        token = auth.create_custom_token(
            str(uid),
            developer_claims=additional_claims or None,
            app=app,
        )
        if isinstance(token, bytes):
            return token.decode('utf-8')
        return str(token)
    except Exception as e:
        logger.error("Failed to mint Firebase custom token for UID %s: %s", uid, e)
        return None


def send_fcm_multicast(
    tokens: list[str],
    title: str = '',
    body: str = '',
    data: dict | None = None,
) -> dict:
    """Send FCM multicast notification to a list of device registration tokens."""
    if not tokens:
        return {'success_count': 0, 'failure_count': 0, 'responses': []}

    app = get_firebase_app()
    if not app:
        return {'success_count': 0, 'failure_count': len(tokens), 'responses': []}

    try:
        from firebase_admin import messaging

        str_data = {str(k): str(v) for k, v in (data or {}).items()}
        notification = None
        if title or body:
            notification = messaging.Notification(title=title, body=body)

        message = messaging.MulticastMessage(
            tokens=tokens,
            notification=notification,
            data=str_data,
        )

        # send_each_for_multicast is preferred in firebase-admin >= 6.2
        if hasattr(messaging, 'send_each_for_multicast'):
            response = messaging.send_each_for_multicast(message, app=app)
        else:
            response = messaging.send_multicast(message, app=app)

        return {
            'success_count': response.success_count,
            'failure_count': response.failure_count,
        }
    except Exception as e:
        logger.error("Failed to send FCM multicast message: %s", e)
        return {'success_count': 0, 'failure_count': len(tokens), 'error': str(e)}
