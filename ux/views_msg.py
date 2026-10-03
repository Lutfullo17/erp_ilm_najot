from django.db.models import Q

from bot.models import TelegramAppeal
from groups_app.models import Group

from .base import UxView
from .utils import paginate

ADMIN = {'administrator', 'director'}


class MessagesView(UxView):
    roles = ADMIN
    template_name = 'new/messages.html'

    def get(self, request):
        qs = TelegramAppeal.objects.select_related('telegram_user', 'student').order_by('-created_at')
        flt = request.GET.get('f', 'open')
        if flt == 'open':
            qs = qs.filter(is_resolved=False)
        elif flt == 'done':
            qs = qs.filter(is_resolved=True)
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(student__first_name__icontains=q) | Q(student__last_name__icontains=q) | Q(message__icontains=q))
        page, qs_params = paginate(request, qs, 15)
        return self.render(request, {
            'page': page, 'qs': qs_params, 'q': q, 'flt': flt,
            'filters': [('open', 'Javob kutayotganlar'), ('done', 'Javob berilgan'), ('all', 'Hammasi')],
            'open_count': TelegramAppeal.objects.filter(is_resolved=False).count(),
            'groups': Group.objects.filter(is_active=True).order_by('name'),
        })
