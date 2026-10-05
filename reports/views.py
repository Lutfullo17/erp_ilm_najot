from datetime import date
from decimal import Decimal

from django.views.generic import TemplateView
from django.db.models import Case, Count, DecimalField, F, Q, Sum, Value, When
from django.db.models.functions import TruncMonth
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404
from users1.views import DirectorRequiredMixin
from payments.billing import add_months
from payments.models import PaymentAllocation, PaymentMethod, PaymentTransaction, StudentMonthBalance
from students.models import Student
from groups_app.models import Group, GroupStudent

from attendance.models import AttendanceRecord, AttendanceSession, AttendanceStatus
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
            roster = list(
                GroupStudent.objects.filter(
                    group=session.group,
                    is_active=True,
                    joined_at__lte=today,
                    student__is_active=True,
                ).select_related('student')
            )
            records = {
                record.student_id: record.status
                for record in session.records.all()
            }
            roster_ids = {membership.student_id for membership in roster}
            statuses = [records.get(student_id) for student_id in roster_ids]
            stats = {
                'group': session.group,
                'teacher': session.teacher,
                'total': len(roster),
                'present': statuses.count(AttendanceStatus.PRESENT),
                'absent': statuses.count(AttendanceStatus.ABSENT),
                'excused': statuses.count(AttendanceStatus.EXCUSED),
                'late': statuses.count(AttendanceStatus.LATE),
                'unmarked': statuses.count(None),
                'session': session,
            }
            attendance_stats.append(stats)

        context['attendance_stats'] = attendance_stats
        context['today'] = today
        return context


class TodayAttendanceDetailView(LoginRequiredMixin, AdminAccessRequiredMixin, TemplateView):
    template_name = 'reports/today_attendance_detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        group = get_object_or_404(Group.objects.select_related('teacher'), pk=self.kwargs['group_id'])
        session = AttendanceSession.objects.filter(group=group, date=today).first()
        records = {}
        if session:
            records = {
                record.student_id: record
                for record in AttendanceRecord.objects.filter(session=session).select_related('student')
            }

        students = list(
            GroupStudent.objects.filter(
                group=group,
                is_active=True,
                joined_at__lte=today,
                student__is_active=True,
            ).select_related('student')
        )
        for membership in students:
            membership.attendance = records.get(membership.student_id)
        context.update({
            'group': group,
            'session': session,
            'students': students,
            'today': today,
            'total': len(students),
            'present': sum(1 for membership in students if membership.attendance and membership.attendance.status == AttendanceStatus.PRESENT),
            'absent': sum(1 for membership in students if membership.attendance and membership.attendance.status == AttendanceStatus.ABSENT),
            'late': sum(1 for membership in students if membership.attendance and membership.attendance.status == AttendanceStatus.LATE),
            'excused': sum(1 for membership in students if membership.attendance and membership.attendance.status == AttendanceStatus.EXCUSED),
            'unmarked': sum(1 for membership in students if not membership.attendance),
        })
        return context


MONEY = DecimalField(max_digits=14, decimal_places=2)


def _parse_month(value, default):
    if value:
        try:
            parsed = date.fromisoformat(value + '-01')
            if 2000 <= parsed.year <= 2100:
                return parsed
        except ValueError:
            pass
    return default


def _capped_paid():
    """Oy uchun to'langan summa (shu oydagi ortiqcha to'lov/avans hisobga olinmaydi)."""
    return Case(
        When(paid_amount__gt=F('required_amount'), then=F('required_amount')),
        default=F('paid_amount'),
        output_field=MONEY,
    )


def _debt_expr():
    return Case(
        When(paid_amount__lt=F('required_amount'), then=F('required_amount') - F('paid_amount')),
        default=Value(Decimal('0')),
        output_field=MONEY,
    )


def _month_aggregates():
    return dict(
        expected=Sum('required_amount'),
        collected=Sum(_capped_paid()),
        debt=Sum(_debt_expr()),
        total_users=Count('id'),
        paid_users=Count('id', filter=Q(paid_amount__gte=F('required_amount'))),
        partial_users=Count('id', filter=Q(paid_amount__gt=0, paid_amount__lt=F('required_amount'))),
        unpaid_users=Count('id', filter=Q(paid_amount=0, required_amount__gt=0)),
    )


def _percent(part, whole):
    return round(float(part) / float(whole) * 100) if whole else 100


class FinanceReportView(LoginRequiredMixin, DirectorRequiredMixin, TemplateView):
    """Moliyaviy hisobot.

    Ikki xil ko'rsatkich atayin alohida ko'rsatiladi:
    * Kassa — tanlangan oyda haqiqatda qabul qilingan pul (to'lov sanasi bo'yicha);
    * Hisoblangan — tanlangan oy uchun o'quvchilardan kutilgan summa, uning qanchasi yopilgani va qarz.
    """
    template_name = 'reports/finance_report.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        this_month = today.replace(day=1)
        selected_month = _parse_month(self.request.GET.get('month'), this_month)
        next_month = add_months(selected_month, 1)
        context.update(
            selected_month=selected_month,
            today=today,
            is_future_month=selected_month > this_month,
        )

        # ---------------- 1. Kassa: shu oyda qabul qilingan pul
        month_payments = PaymentTransaction.objects.filter(
            payment_date__gte=selected_month, payment_date__lt=next_month,
        )
        cash = month_payments.aggregate(
            total=Sum('amount'),
            count=Count('id'),
            cash=Sum('amount', filter=Q(method=PaymentMethod.CASH)),
            card=Sum('amount', filter=Q(method=PaymentMethod.CARD)),
            transfer=Sum('amount', filter=Q(method=PaymentMethod.TRANSFER)),
        )
        split = PaymentAllocation.objects.filter(payment__in=month_payments).aggregate(
            this=Sum('amount', filter=Q(balance__month=selected_month)),
            past=Sum('amount', filter=Q(balance__month__lt=selected_month)),
            future=Sum('amount', filter=Q(balance__month__gt=selected_month)),
        )
        context['cash'] = {
            'total': cash['total'] or 0,
            'count': cash['count'],
            'cash': cash['cash'] or 0,
            'card': cash['card'] or 0,
            'transfer': cash['transfer'] or 0,
            'for_this_month': split['this'] or 0,
            'for_past_months': split['past'] or 0,
            'for_future_months': split['future'] or 0,
        }

        # ---------------- 2. Hisoblangan: shu oy uchun (faqat to'lov muddati kelgan o'quvchilar)
        month_balances = StudentMonthBalance.objects.filter(month=selected_month)
        due_balances = month_balances.due(today)
        month_stats = {k: (v or 0) for k, v in due_balances.aggregate(**_month_aggregates()).items()}
        month_stats['percent'] = _percent(month_stats['collected'], month_stats['expected'])
        # O'quvchilar soni: bir nechta guruhdagi o'quvchi bir marta sanaladi
        per_student = list(due_balances.values('student').annotate(
            debt=Sum(_debt_expr()), paid=Sum('paid_amount'), required=Sum('required_amount'),
        ))
        month_stats['total_students'] = len(per_student)
        month_stats['paid_students'] = sum(1 for r in per_student if not r['debt'])
        month_stats['unpaid_students'] = sum(1 for r in per_student if r['debt'] and not r['paid'])
        month_stats['partial_students'] = (
            month_stats['total_students'] - month_stats['paid_students'] - month_stats['unpaid_students']
        )
        context['month_stats'] = month_stats
        context['not_due'] = month_balances.not_due(today).aggregate(count=Count('id'), paid=Sum('paid_amount'))

        # ---------------- 3. Umumiy holat (bugungi kun bo'yicha, barcha oylar)
        all_debts = StudentMonthBalance.objects.debts(today)
        current_debts = all_debts.current_members()
        former_debts = all_debts.former_members()
        context['overall'] = {
            'debt': current_debts.aggregate(s=Sum(_debt_expr()))['s'] or 0,
            'debtors': current_debts.values('student').distinct().count(),
            'former_debt': former_debts.aggregate(s=Sum(_debt_expr()))['s'] or 0,
            'former_debtors': former_debts.values('student').distinct().count(),
            'advance': StudentMonthBalance.objects.not_due(today).aggregate(s=Sum('paid_amount'))['s'] or 0,
            'total_income': PaymentTransaction.objects.aggregate(s=Sum('amount'))['s'] or 0,
            'active_students': Student.objects.filter(is_active=True).count(),
            'active_groups': Group.objects.filter(is_active=True).count(),
        }

        # ---------------- 4. Guruhlar kesimida
        group_rows = due_balances.values(
            'group_id', 'group__name', 'group__teacher__first_name', 'group__teacher__last_name',
        ).annotate(**_month_aggregates()).order_by('group__name')
        group_stats = []
        for g in group_rows:
            teacher = f"{g['group__teacher__first_name'] or ''} {g['group__teacher__last_name'] or ''}".strip()
            group_stats.append({
                'group': {'id': g['group_id'], 'name': g['group__name'], 'teacher': teacher},
                'total_students': g['total_users'],
                'paid': g['paid_users'],
                'partial': g['partial_users'],
                'unpaid': g['unpaid_users'],
                'expected': g['expected'] or 0,
                'collected': g['collected'] or 0,
                'debt': g['debt'] or 0,
                'percent': _percent(g['collected'] or 0, g['expected'] or 0),
            })
        context['group_stats'] = sorted(group_stats, key=lambda x: (x['percent'], x['group']['name']))

        # ---------------- 5. Oxirgi 12 oy kassasi (tanlangan oy bilan tugaydi)
        first = add_months(selected_month, -11)
        rows = (
            PaymentTransaction.objects.filter(payment_date__gte=first, payment_date__lt=next_month)
            .annotate(m=TruncMonth('payment_date')).values('m').annotate(total=Sum('amount'))
        )
        by_month = {(r['m'].date() if hasattr(r['m'], 'date') else r['m']): r['total'] for r in rows}
        months = [add_months(first, i) for i in range(12)]
        peak = max([by_month.get(m) or 0 for m in months])
        context['monthly_income'] = [
            {
                'month': m,
                'total': by_month.get(m) or 0,
                'width': round(float(by_month.get(m) or 0) / float(peak) * 100) if peak else 0,
                'is_selected': m == selected_month,
            }
            for m in reversed(months)
        ]
        return context
