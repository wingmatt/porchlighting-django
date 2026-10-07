"""Middleware for guest and token authentication."""
import uuid


class GuestAuthMiddleware:
    """Extract guest token and guest name from request headers."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        guest_token = request.headers.get('X-Guest-Token')
        guest_name = request.headers.get('X-Guest-Name')
        request.guest_token = guest_token
        request.guest_name = guest_name
        request.correlation_id = str(uuid.uuid4())
        response = self.get_response(request)
        response['X-Request-ID'] = request.correlation_id
        return response
