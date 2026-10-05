import datetime

from django.utils import timezone

from attendance.models import AttendanceRecord
from reports.views import FinanceReportView, TodayAttendanceView

from .base import UxView


def _context_of(view_cls, request):
    """Eski hisobot view'ining ma'lumotlarini (hisob-kitob mantig'ini) o'zgartirmasdan qayta ishlatadi."""
    v = view_cls()
    v.request, v.args, v.kwargs = request, (), {}
    return v.get_context_data()


class FinanceReportNewView(UxView):
    roles = {'director'}
    template_name = 'new/report.html'

    def get(self, request):
        ctx = _context_of(FinanceReportView, request)
        ctx['month_value'] = ctx['selected_month'].strftime('%Y-%m')
        return self.render(request, ctx)


class TodayAttendanceNewView(UxView):
    roles = {'director', 'administrator'}
    template_name = 'new/report_attendance.html'

    def get(self, request):
        ctx = _context_of(TodayAttendanceView, request)
        today = timezone.localdate()
        ctx['week_total'] = AttendanceRecord.objects.filter(session__date__range=[today - datetime.timedelta(days=6), today]).count()
        ctx['month_total'] = AttendanceRecord.objects.filter(session__date__year=today.year, session__date__month=today.month).count()
        return self.render(request, ctx)
