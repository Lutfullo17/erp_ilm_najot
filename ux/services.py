"""Yangi UI uchun faqat o'qish ma'lumotlari (bosh sahifa va ro'yxatlar). Mavjud modellar ustida."""
import datetime
from decimal import Decimal

from django.db.models import Count, F, Q, Sum
from django.utils import timezone

from attendance.models import AttendanceSession
from groups_app.models import Group
from payments.models import PaymentTransaction, StudentMonthBalance
from students.models import Student

DAY_NAMES = ['Dushanba', 'Seshanba', 'Chorshanba', 'Payshanba', 'Juma', 'Shanba', 'Yakshanba']
ZERO = Decimal('0')


def lesson_end(group):
    if group.end_time:
        return group.end_time
    if group.lesson_time and group.duration:
        td = datetime.timedelta(hours=float(group.duration))
        return (datetime.datetime.combine(datetime.date.today(), group.lesson_time) + td).time()
    return None


def lessons_today(teacher=None, now=None):
    """Bugungi darslar: [{group, start, end, state: upcoming|now|ended, taken: bool, students: int}]"""
    now = now or timezone.localtime()
    today, now_t = now.date(), now.time()
    name = DAY_NAMES[today.weekday()]
    qs = Group.objects.filter(is_active=True, is_paused=False).exclude(lesson_days='').exclude(lesson_time__isnull=True)
    if teacher is not None:
        qs = qs.filter(teacher=teacher)
    qs = qs.select_related('teacher').annotate(
        n_students=Count('groupstudent', filter=Q(groupstudent__is_active=True, groupstudent__student__is_active=True)))
    taken = set(AttendanceSession.objects.filter(date=today, records__isnull=False).values_list('group_id', flat=True))
    out = []
    for g in qs.order_by('lesson_time'):
        days = {d.strip() for d in g.lesson_days.split(',')}
        if name not in days or (g.start_date and g.start_date > today):
            continue
        end = lesson_end(g)
        if now_t < g.lesson_time:
            state = 'upcoming'
        elif end is None or now_t <= end:
            state = 'now'
        else:
            state = 'ended'
        out.append({'group': g, 'start': g.lesson_time, 'end': end, 'state': state,
                    'taken': g.pk in taken, 'students': g.n_students})
    return out


def debt_summary():
    qs = StudentMonthBalance.objects.debts().current_members()
    total = qs.aggregate(s=Sum(F('required_amount') - F('paid_amount')))['s'] or ZERO
    return {'students': qs.values('student').distinct().count(), 'total': total}


def payments_today(user):
    today = timezone.localdate()
    qs = PaymentTransaction.objects.filter(payment_date=today)
    if not user.is_director:
        qs = qs.filter(created_by=user)
    agg = qs.aggregate(total=Sum('amount'), n=Count('id'))
    return {'total': agg['total'] or ZERO, 'count': agg['n']}


def birthdays_today():
    today = timezone.localdate()
    return list(Student.objects.filter(is_active=True, birth_date__month=today.month, birth_date__day=today.day)[:10])


def end_from(start, duration):
    td = datetime.timedelta(hours=float(duration))
    return (datetime.datetime.combine(datetime.date.today(), start) + td).time()


def slot_conflicts(days, start, end, exclude_pk=None):
    """Berilgan kun/vaqt bilan to'qnashadigan faol guruhlar."""
    out = []
    qs = Group.objects.filter(is_active=True, lesson_time__isnull=False).select_related('teacher')
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    for g in qs:
        gdays = {d.strip() for d in (g.lesson_days or '').split(',') if d.strip()}
        if not (gdays & set(days)):
            continue
        gend = g.end_time or lesson_end(g)
        if gend and start < gend and end > g.lesson_time:
            out.append(g)
    return out
