from datetime import date
from decimal import Decimal, InvalidOperation

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from groups_app.models import Group
from students.models import Student

from bot.notifications import notify_payment_received, notify_payment_deleted
from .billing import add_months, current_due_month, sync_pair
from .models import (
    MonthBalanceStatus,
    PaymentMethod,
    PaymentTransaction,
    StudentMonthBalance,
)


class PaymentInputError(ValueError):
    pass


def first_day_of_month(value):
    if isinstance(value, date):
        return value.replace(day=1)

    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError):
        raise PaymentInputError("Sana YYYY-MM-DD formatida bo'lishi kerak.")

    return parsed.replace(day=1)


def parse_payment_date(value):
    if value in (None, ''):
        return timezone.localdate()
    if isinstance(value, date):
        return value

    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise PaymentInputError("To'lov sanasi YYYY-MM-DD formatida bo'lishi kerak.")


def next_month(value):
    return add_months(value, 1)


def parse_money(value, field_name='amount'):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise PaymentInputError(
            f"{field_name} noto'g'ri son bo'lishi kerak."
        )
    if not amount.is_finite():
        raise PaymentInputError(f"{field_name} noto'g'ri son bo'lishi kerak.")

    amount = amount.quantize(Decimal('0.01'))
    if amount < 0:
        raise PaymentInputError(f'{field_name} 0 dan kichik bo\'lishi mumkin emas.')
    if amount > Decimal('1000000000'):
        raise PaymentInputError(f'{field_name} juda katta qiymat.')
    return amount


def assert_admin_user(user):
    if not hasattr(user, 'is_authenticated') or not hasattr(user, 'is_admin_access'):
        raise PermissionDenied('Foydalanuvchi obyektida kerakli atributlar yo\'q.')
    if not user.is_authenticated:
        raise PermissionDenied('Login talab qilinadi.')
    if not user.is_admin_access:
        raise PermissionDenied('Faqat admin yoki director to\'lov qabul qila oladi.')


def get_payment_group(group_id):
    # Yopilgan guruh ham qaytariladi: undagi eski qarzlarni undirish mumkin bo'lishi kerak.
    return get_object_or_404(Group, pk=group_id)


def is_current_member(student, group):
    return (
        student.is_active and group.is_active
        and group.groupstudent_set.filter(student=student, is_active=True).exists()
    )


def outstanding_debt(student, group):
    rows = StudentMonthBalance.objects.debts().filter(student=student, group=group)
    return sum((b.debt_amount for b in rows), Decimal('0'))


def get_payment_student(student_id, group):
    """Hozirgi a'zo — istalgan to'lov; sobiq a'zo (ketgan, chiqqan, guruh yopilgan) — faqat qarzini to'lashi mumkin."""
    student = get_object_or_404(Student, pk=student_id)
    if is_current_member(student, group) or outstanding_debt(student, group) > 0:
        return student
    raise PaymentInputError("O'quvchi ushbu guruhga biriktirilmagan.")


def serialize_money(value):
    value = Decimal(value).quantize(Decimal('0.01'))
    return str(value.quantize(Decimal('1')) if value == value.to_integral() else value)


def serialize_balance(balance):
    is_due = balance.is_due
    return {
        'id': balance.id,
        'month': balance.month.isoformat(),
        'due_date': balance.due_date.isoformat() if balance.due_date else None,
        'is_due': is_due,
        'required_amount': serialize_money(balance.required_amount),
        'paid_amount': serialize_money(balance.paid_amount),
        # Muddati kelmagan oy qarz emas: undagi pul — oldindan to'lov (avans).
        'debt_amount': serialize_money(balance.debt_amount if is_due else 0),
        'advance_amount': serialize_money(balance.advance_amount if is_due else balance.paid_amount),
        'status': balance.status,
        'status_label': balance.get_status_display() if is_due else "Oldindan to'lov",
    }


def build_payment_summary(balances, payment_month):
    current_month_status = None
    closed_months_count = 0
    advance_amount = Decimal('0')
    debt_amount = Decimal('0')

    for balance in balances:
        if balance.status == MonthBalanceStatus.CLOSED:
            closed_months_count += 1
        if balance.month == payment_month:
            current_month_status = balance.status
            debt_amount = balance.debt_amount
        if not balance.is_due:
            advance_amount += balance.paid_amount
        elif balance.advance_amount > 0:
            advance_amount += balance.advance_amount

    return {
        'current_month_status': current_month_status,
        'closed_months_count': closed_months_count,
        'advance_amount': serialize_money(advance_amount),
        'debt_amount': serialize_money(debt_amount),
        'remaining_amount': '0',
    }


def get_student_payment_state(student_id, group_id, from_month=None, months=6):
    """To'lov formasi uchun holat: barcha qarzli oylar, oxirgi `months` oy va avanslar."""
    group = get_payment_group(group_id)
    student = get_payment_student(student_id, group)
    today = timezone.localdate()
    sync_pair(student, group, as_of=today)

    qs = StudentMonthBalance.objects.filter(student=student, group=group).order_by('month')
    cur = current_due_month(group, today)
    if from_month:
        window_start = first_day_of_month(from_month)
    elif cur is not None:
        window_start = add_months(cur, -(max(1, months) - 1))
    else:
        window_start = None

    balances = [
        b for b in qs
        if window_start is None
        or b.month >= window_start            # oxirgi oylar va avanslar
        or b.paid_amount < b.required_amount  # eski qarzlar doim ko'rinadi
    ]

    return {
        'student': {'id': student.id, 'full_name': str(student)},
        'group': {'id': group.id, 'name': group.name, 'monthly_fee': serialize_money(group.monthly_fee or 0)},
        'balances': [serialize_balance(b) for b in balances],
    }


@transaction.atomic
def apply_payment(user, student_id, group_id, amount, payment_date=None, method=PaymentMethod.CASH, note=''):
    assert_admin_user(user)

    group = get_payment_group(group_id)
    student = get_payment_student(student_id, group)
    if group.monthly_fee is None:
        raise PaymentInputError(
            f"'{group.name}' guruhining oylik to'lovi kiritilmagan. Avval guruh narxini belgilang."
        )

    payment_date = parse_payment_date(payment_date)
    today = timezone.localdate()
    if payment_date > today:
        raise PaymentInputError("To'lov sanasi kelajakda bo'lishi mumkin emas.")

    amount = parse_money(amount)
    if amount <= 0:
        raise PaymentInputError("To'lov summasi 0 dan katta bo'lishi kerak.")

    if not is_current_member(student, group):
        # Sobiq a'zoning kelgusi oylari yo'q — ortiqcha summa hech qaysi oyga tushmay "osilib" qoladi.
        debt = outstanding_debt(student, group)
        if amount > debt:
            raise PaymentInputError(
                f"O'quvchi bu guruhda endi o'qimaydi. Faqat qolgan qarzini ({serialize_money(debt)} so'm) to'lashi mumkin."
            )

    method = method or PaymentMethod.CASH
    if method not in PaymentMethod.values:
        raise PaymentInputError("To'lov turi noto'g'ri.")

    note_str = str(note or '').strip()
    if len(note_str) > 255:
        raise PaymentInputError("Izoh 255 belgidan oshmasligi kerak.")

    payment = PaymentTransaction(
        student=student,
        group=group,
        amount=amount,
        payment_date=payment_date,
        method=method,
        created_by=user,
        note=note_str,
    )
    payment._skip_sync = True  # quyida o'zimiz sync qilamiz
    payment.save()

    sync_pair(student, group, as_of=today)

    allocations = list(payment.allocations.select_related('balance').order_by('balance__month'))
    balances = [a.balance for a in allocations]

    def _notify():
        try:
            notify_payment_received(payment)
        except Exception:
            pass
    transaction.on_commit(_notify)

    return {
        'payment': {
            'id': payment.id,
            'amount': serialize_money(payment.amount),
            'payment_date': payment.payment_date.isoformat(),
            'method': payment.method,
        },
        'student': {'id': student.id, 'full_name': str(student)},
        'group': {'id': group.id, 'name': group.name, 'monthly_fee': serialize_money(group.monthly_fee)},
        'allocations': [
            dict(serialize_balance(a.balance), allocated_amount=serialize_money(a.amount)) for a in allocations
        ],
        'summary': build_payment_summary(balances, first_day_of_month(payment_date)),
        'remaining': '0',
    }


@transaction.atomic
def delete_payment(user, payment_id):
    if not user.is_director:
        raise PermissionDenied("Faqat direktor to'lovlarni o'chira oladi.")

    payment = get_object_or_404(PaymentTransaction.objects.select_related('student', 'group'), pk=payment_id)
    student, group = payment.student, payment.group
    snapshot = PaymentTransaction(
        pk=payment.pk, student=student, group=group, amount=payment.amount,
        payment_date=payment.payment_date, method=payment.method,
    )

    payment._skip_sync = True
    payment.delete()  # taqsimotlar CASCADE bilan o'chadi
    sync_pair(student, group)  # qolgan to'lovlar qayta taqsimlanadi

    def _notify():
        try:
            notify_payment_deleted(snapshot)
        except Exception:
            pass
    transaction.on_commit(_notify)
    return True
