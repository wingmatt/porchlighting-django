"""URL routing for accounts app."""
from django.urls import path
from .views import (
    FCMDeviceRegisterView,
    FCMDeviceUnregisterView,
    FirebaseCustomTokenView,
    LoginView,
    LogoutView,
    MeView,
    RegisterView,
)

app_name = 'accounts'

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', LoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('me/', MeView.as_view(), name='me'),
    path('firebase-token/', FirebaseCustomTokenView.as_view(), name='firebase-token'),
    path('fcm/register/', FCMDeviceRegisterView.as_view(), name='fcm-register'),
    path('fcm/unregister/', FCMDeviceUnregisterView.as_view(), name='fcm-unregister'),
    path('fcm-token/', FCMDeviceRegisterView.as_view(), name='fcm-token'),
]
