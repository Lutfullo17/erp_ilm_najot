"""Yangi UI uchun umumiy view yordamchilari: kirish, rol va bloklanganlikni tekshirish."""
import json
from functools import wraps

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views import View

from .nav import role_of

LOGIN_URL = '/users/login/'


def _deny(request, json_mode):
    if json_mode:
        return JsonResponse({'detail': "Ruxsat yo'q."}, status=403)
    messages.error(request, "Bu bo'limga kirish huquqingiz yo'q.")
    return redirect('new:home')


def ux_login(roles=None, json_mode=False):
    """Funksional view uchun dekorator. roles: {'administrator','director','teacher'} yoki None (hamma)."""
    def deco(fn):
        @wraps(fn)
        def wrapper(request, *args, **kwargs):
            user = request.user
            if not user.is_authenticated:
                if json_mode:
                    return JsonResponse({'detail': 'Tizimga kiring.'}, status=401)
                return redirect(f'{LOGIN_URL}?next={request.path}')
            if getattr(user, 'is_blocked', False):
                return redirect(LOGIN_URL)
            if roles and role_of(user) not in roles:
                return _deny(request, json_mode)
            return fn(request, *args, **kwargs)
        return wrapper
    return deco


class UxView(View):
    """Sinfli view. `roles` — ruxsat etilgan rollar; `template_name` — shablon."""
    roles = None
    template_name = None
    json_mode = False

    def dispatch(self, request, *args, **kwargs):
        handler = ux_login(self.roles, self.json_mode)(super().dispatch)
        return handler(request, *args, **kwargs)

    def render(self, request, ctx=None, status=200):
        context = {'role': role_of(request.user)}
        context.update(ctx or {})
        return render(request, self.template_name, context, status=status)


def json_body(request):
    try:
        return json.loads(request.body.decode('utf-8') or '{}')
    except (ValueError, UnicodeDecodeError):
        return None
