"""URL routing for accounts app."""
from django.urls import path
from .views import (
    FCMDeviceRegisterView,
    FCMDeviceUnregisterView,
    FirebaseCustomTokenView,
    ConfirmEmailView,
    LoginView,
    MagicLoginConfirmView,
    MagicLoginRequestView,
    LogoutView,
    MeView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    RegisterView,
)

app_name = 'accounts'

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('confirm-email/<uidb64>/<token>/', ConfirmEmailView.as_view(), name='confirm-email'),
    path('login/', LoginView.as_view(), name='login'),
    path('password-reset/', PasswordResetRequestView.as_view(), name='password-reset'),
    path('password-reset/<uidb64>/<token>/', PasswordResetConfirmView.as_view(), name='password-reset-confirm'),
    path('magic-login/', MagicLoginRequestView.as_view(), name='magic-login'),
    path('magic-login/<uidb64>/<token>/', MagicLoginConfirmView.as_view(), name='magic-login-confirm'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('me/', MeView.as_view(), name='me'),
    path('firebase-token/', FirebaseCustomTokenView.as_view(), name='firebase-token'),
    path('fcm/register/', FCMDeviceRegisterView.as_view(), name='fcm-register'),
    path('fcm/unregister/', FCMDeviceUnregisterView.as_view(), name='fcm-unregister'),
    path('fcm-token/', FCMDeviceRegisterView.as_view(), name='fcm-token'),
]
