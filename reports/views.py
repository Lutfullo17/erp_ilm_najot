from datetime import date
from django.views.generic import TemplateView
from django.db.models import Sum, Count, Q
from django.db.models.functions import TruncMonth
from django.contrib.auth.mixins import LoginRequiredMixin
from users1.views import DirectorRequiredMixin
from payments.models import PaymentTransaction, StudentMonthBalance, MonthBalanceStatus
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
        
        # Month Filter
        selected_month_str = self.request.GET.get('month')
        if selected_month_str:
            try:
                selected_month = date.fromisoformat(selected_month_str + '-01')
            except ValueError:
                selected_month = date.today().replace(day=1)
        else:
            selected_month = date.today().replace(day=1)
        
        context['selected_month'] = selected_month
        
        # Monthly income for the last 12 months
        monthly_income = PaymentTransaction.objects.annotate(
            month=TruncMonth('payment_date')
        ).values('month').annotate(
            total=Sum('amount')
        ).order_by('-month')[:12]
        
        context['monthly_income'] = monthly_income
        
        # Overall Totals (Lifetime)
        context['total_income'] = PaymentTransaction.objects.aggregate(total=Sum('amount'))['total'] or 0
        context['total_students_count'] = Student.objects.filter(is_active=True).count()
        context['total_groups_count'] = Group.objects.filter(is_active=True).count()
        
        # Selected Month Statistics
        month_balances = StudentMonthBalance.objects.filter(month=selected_month)
        month_totals = month_balances.aggregate(
            expected=Sum('required_amount'),
            collected=Sum('paid_amount'),
            paid_users=Count('id', filter=Q(status=MonthBalanceStatus.CLOSED)),
            partial_users=Count('id', filter=Q(status=MonthBalanceStatus.PARTIAL)),
            unpaid_users=Count('id', filter=Q(status=MonthBalanceStatus.OPEN)),
            total_users=Count('id')
        )
        
        context['month_stats'] = {
            'expected': month_totals['expected'] or 0,
            'collected': month_totals['collected'] or 0,
            'debt': (month_totals['expected'] or 0) - (month_totals['collected'] or 0),
            'paid_users': month_totals['paid_users'],
            'partial_users': month_totals['partial_users'],
            'unpaid_users': month_totals['unpaid_users'],
            'total_users': month_totals['total_users'],
        }
        
        # Group-wise Stats for Selected Month (Optimized)
        from django.db.models import F
        group_stats_qs = month_balances.values(
            'group_id', 'group__name'
        ).annotate(
            total_students=Count('id'),
            expected=Sum('required_amount'),
            collected=Sum('paid_amount'),
            paid=Count('id', filter=Q(status=MonthBalanceStatus.CLOSED)),
            partial=Count('id', filter=Q(status=MonthBalanceStatus.PARTIAL)),
            unpaid=Count('id', filter=Q(status=MonthBalanceStatus.OPEN)),
            debt=Sum(F('required_amount') - F('paid_amount'))
        ).order_by('group__name')

        group_stats = []
        for g in group_stats_qs:
            expected = g['expected'] or 0
            collected = g['collected'] or 0
            percent = (float(collected) / float(expected) * 100) if expected > 0 else 0
            
            group_stats.append({
                'group': {'id': g['group_id'], 'name': g['group__name']},
                'total_students': g['total_students'],
                'paid': g['paid'],
                'partial': g['partial'],
                'unpaid': g['unpaid'],
                'expected': expected,
                'collected': collected,
                'debt': g['debt'],
                'percent': percent,
            })
            
        context['group_stats'] = sorted(group_stats, key=lambda x: x['percent'])
        
        return context
