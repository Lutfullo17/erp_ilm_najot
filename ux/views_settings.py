from django.db.models import Q

from bot.models import TelegramUser
from users1.models import AuditLog
from users1.views import BotStatusView, TeacherProfileView

from .base import UxView
from .models import Feedback
from .utils import paginate
from .views_reports import _context_of


class SettingsView(UxView):
    roles = {'director', 'administrator'}
    template_name = 'new/settings.html'

    def get(self, request):
        ctx = {}
        if request.user.is_director:
            ctx['feedback'] = Feedback.objects.select_related('user')[:15]
        return self.render(request, ctx)


class TelegramStatusView(UxView):
    roles = {'director', 'administrator'}
    template_name = 'new/telegram.html'

    def get(self, request):
        ctx = _context_of(BotStatusView, request)
        page, qs = paginate(request, ctx['students'], 25)
        ctx.update({'page': page, 'qs': qs, 'status': ctx['current_status']})
        ctx['tabs'] = [('connected', 'Ulangan'), ('not_connected', 'Ulanmagan'), ('telegram_blocked', 'Botni bloklagan'), ('blocked', "O'chirilgan/bloklangan o'quvchilar")]
        ids = [s.pk for s in page.object_list]
        ctx['tg'] = {t.student_id: t for t in TelegramUser.objects.filter(student_id__in=ids, is_verified=True)}
        return self.render(request, ctx)


class AuditView(UxView):
    roles = {'director'}
    template_name = 'new/audit.html'

    def get(self, request):
        qs = AuditLog.objects.select_related('user', 'target_user').order_by('-created_at')
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(action__icontains=q) | Q(user__username__icontains=q) | Q(user__first_name__icontains=q) | Q(target_user__username__icontains=q))
        page, qs_params = paginate(request, qs, 30)
        return self.render(request, {'page': page, 'qs': qs_params, 'q': q})


class ProfileView(UxView):
    roles = {'teacher'}
    template_name = 'new/profile.html'

    def get(self, request):
        v = TeacherProfileView()
        v.request, v.args, v.kwargs = request, (), {}
        return self.render(request, v.get_context_data())
