"""Master URL Configuration for Porchlight Django."""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path


def api_root_view(request):
    """API overview endpoint."""
    return JsonResponse(
        {
            'name': 'Porchlight Django API',
            'version': '1.0.0',
            'status': 'healthy',
            'endpoints': {
                'auth': {
                    'register': '/api/auth/register/',
                    'login': '/api/auth/login/',
                    'logout': '/api/auth/logout/',
                    'me': '/api/auth/me/',
                    'firebase_token': '/api/auth/firebase-token/',
                    'fcm_register': '/api/auth/fcm/register/',
                    'fcm_unregister': '/api/auth/fcm/unregister/',
                },
                'porchlights': {
                    'list_create': '/api/porchlights/',
                    'detail': '/api/porchlights/<id>/',
                    'control': '/api/porchlights/<id>/control/',
                    'members': '/api/porchlights/<id>/members/',
                    'permissions': '/api/porchlights/<id>/permissions/',
                    'rsvps': '/api/porchlights/<id>/rsvps/',
                },
                'beacons': {
                    'list_create': '/api/beacons/',
                    'detail': '/api/beacons/<id>/',
                    'control': '/api/beacons/<id>/control/',
                    'members': '/api/beacons/<id>/members/',
                    'permissions': '/api/beacons/<id>/permissions/',
                    'rsvps': '/api/beacons/<id>/rsvps/',
                },
                'invitations': {
                    'list_create': '/api/invitations/',
                    'detail': '/api/invitations/<id>/',
                    'validate': '/api/invitations/validate/<code>/',
                    'accept': '/api/invitations/accept/',
                },
                'rsvps': {
                    'list_create': '/api/rsvps/',
                    'detail': '/api/rsvps/<id>/',
                },
                'permissions': {
                    'list_create': '/api/permissions/',
                },
                'guest': {
                    'access': '/api/guest/access/',
                },
                'admin': '/admin/',
            },
        }
    )


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', api_root_view, name='api-root'),
    path('api/auth/', include('apps.accounts.urls', namespace='accounts')),
    path('api/', include('apps.porchlights.urls', namespace='porchlights')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
