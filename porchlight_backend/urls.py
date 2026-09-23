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
                },
                'porchlights': {
                    'list_create': '/api/porchlights/',
                    'detail': '/api/porchlights/<id>/',
                    'control': '/api/porchlights/<id>/control/',
                    'members': '/api/porchlights/<id>/members/',
                },
                'invitations': {
                    'list_create': '/api/invitations/',
                    'validate': '/api/invitations/validate/<code>/',
                    'accept': '/api/invitations/accept/',
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
