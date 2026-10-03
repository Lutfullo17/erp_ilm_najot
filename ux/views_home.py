from django.contrib import messages
from django.shortcuts import redirect
from django.utils import timezone

from attendance.models import AttendanceSession
from bot.models import TelegramAppeal
from payments.models import PaymentTransaction
from users1.models import MissedAttendanceAlert, ScheduleChangeRequest, TeacherPenalty
from django.db.models import Sum

from . import services
from .base import UxView, ux_login
from .flags import COOKIE
from .templatetags.ux_tags import som


def switch_ui(request, which):
    """Eski va yangi ko'rinish o'rtasida almashish (cookie, 1 yil)."""
    if which == 'new':
        resp = redirect('new:home')
    else:
        resp = redirect('users1:index')
    if request.user.is_authenticated:
        resp.set_cookie(COOKIE, 'new' if which == 'new' else 'old', max_age=365 * 24 * 3600, samesite='Lax')
    return resp


class HomeView(UxView):
    def get(self, request):
        user = request.user
        today = timezone.localdate()
        if user.is_teacher:
            self.template_name = 'new/home_teacher.html'
            lessons = services.lessons_today(teacher=user)
            current = next((l for l in lessons if l['state'] == 'now'), None)
            month_points = TeacherPenalty.objects.filter(
                teacher=user, created_at__year=today.year, created_at__month=today.month,
            ).aggregate(s=Sum('points'))['s'] or 0
            missed = MissedAttendanceAlert.objects.filter(
                teacher=user, status=MissedAttendanceAlert.Status.PENDING).select_related('group')[:5]
            return self.render(request, {
                'lessons': lessons, 'current': current, 'month_points': month_points, 'missed': missed,
            })

        lessons = services.lessons_today()
        waiting = [l for l in lessons if not l['taken'] and l['state'] in ('now', 'ended')]
        ctx = {
            'debt': services.debt_summary(),
            'paid_today': services.payments_today(user),
            'lessons': lessons,
            'waiting': waiting,
            'appeals': TelegramAppeal.objects.filter(is_resolved=False).count(),
            'requests': ScheduleChangeRequest.objects.filter(status=ScheduleChangeRequest.Status.PENDING).count(),
            'birthdays': services.birthdays_today(),
        }
        ctx['debt_sub'] = f"Jami qarz: {som(ctx['debt']['total'])} so'm"
        ctx['paid_sub'] = f"{ctx['paid_today']['count']} ta to'lov"
        if user.is_director:
            self.template_name = 'new/home_director.html'
            month = PaymentTransaction.objects.filter(
                payment_date__year=today.year, payment_date__month=today.month).aggregate(s=Sum('amount'))['s'] or 0
            ctx['month_income'] = month
            ctx['missed_today'] = MissedAttendanceAlert.objects.filter(lesson_date=today).select_related('teacher', 'group')[:8]
        else:
            self.template_name = 'new/home_admin.html'
        return self.render(request, ctx)
