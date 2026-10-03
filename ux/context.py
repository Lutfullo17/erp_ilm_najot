from .flags import new_ui_visible
from .nav import menu_for


def ux_context(request):
    user = getattr(request, 'user', None)
    if user is None or not user.is_authenticated:
        return {}
    ctx = {'new_ui_available': new_ui_visible(user)}
    if request.path.startswith('/new/'):
        ctx.update(menu_for(user, request.path))
    return ctx
