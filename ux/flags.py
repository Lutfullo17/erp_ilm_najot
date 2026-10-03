"""Yangi UI ni yoqish: cookie (`ui=new|old`) > NEW_UI_USERS env ('*' = hamma). Bo'sh bo'lsa hamma eskisida."""
from django.conf import settings

COOKIE = 'ui'


def _flag_users():
    return {u.strip() for u in getattr(settings, 'NEW_UI_USERS', []) if u.strip()}


def new_ui_enabled(request):
    user = getattr(request, 'user', None)
    if user is None or not user.is_authenticated:
        return False
    choice = request.COOKIES.get(COOKIE)
    if choice == 'new':
        return True
    if choice == 'old':
        return False
    users = _flag_users()
    return '*' in users or user.username in users


def new_ui_visible(user):
    """Eski sahifalarda "Yangi ko'rinishni sinash" havolasi ko'rinsinmi."""
    if not user.is_authenticated:
        return False
    return bool(getattr(settings, 'NEW_UI_OPT_IN', False) or _flag_users())
