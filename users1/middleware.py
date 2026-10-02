from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect


class BlockedUserMiddleware:
    """Bloklangan foydalanuvchining mavjud sessiyasini darhol tugatadi."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        if user is not None and user.is_authenticated and getattr(user, 'is_blocked', False):
            logout(request)
            messages.error(request, "Sizning akkauntingiz bloklangan. Director bilan bog'laning.")
            return redirect('users1:login')
        return self.get_response(request)
