from django.views.generic import TemplateView
from django.db.models import Sum
from django.db.models.functions import TruncMonth
from django.contrib.auth.mixins import LoginRequiredMixin
from users1.views import DirectorRequiredMixin
from payments.models import PaymentTransaction
from students.models import Student
from groups_app.models import Group

from attendance.models import AttendanceSession, AttendanceStatus
from django.utils import timezone
from users1.views import AdminAccessRequiredMixin

class TodayAttendanceView(LoginRequiredMixin, AdminAccessRequiredMixin, TemplateView):
    template_name = 'reports/today_attendance.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        sessions = AttendanceSession.objects.filter(date=today).select_related('group', 'teacher').prefetch_related('records')
        
        attendance_stats = []
        for session in sessions:
            records = session.records.all()
            stats = {
                'group': session.group,
                'teacher': session.teacher,
                'total': records.count(),
                'present': sum(1 for r in records if r.status == AttendanceStatus.PRESENT),
                'absent': sum(1 for r in records if r.status == AttendanceStatus.ABSENT),
                'excused': sum(1 for r in records if r.status == AttendanceStatus.EXCUSED),
                'late': sum(1 for r in records if r.status == AttendanceStatus.LATE),
            }
            attendance_stats.append(stats)
            
        context['attendance_stats'] = attendance_stats
        context['today'] = today
        return context

class FinanceReportView(LoginRequiredMixin, DirectorRequiredMixin, TemplateView):
    template_name = 'reports/finance_report.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Monthly income for the last 12 months
        monthly_income = PaymentTransaction.objects.annotate(
            month=TruncMonth('payment_date')
        ).values('month').annotate(
            total=Sum('amount')
        ).order_by('-month')[:12]
        
        context['monthly_income'] = monthly_income
        
        # Totals
        context['total_income'] = PaymentTransaction.objects.aggregate(total=Sum('amount'))['total'] or 0
        context['total_students'] = Student.objects.filter(is_active=True).count()
        context['total_groups'] = Group.objects.filter(is_active=True).count()
        
        return context
