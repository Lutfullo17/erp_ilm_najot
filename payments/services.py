from datetime import date
from decimal import Decimal, InvalidOperation

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404

from groups_app.models import Group
from students.models import Student

from .models import PaymentAllocation, PaymentMethod, PaymentTransaction, StudentMonthBalance


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
    if value is None:
        return date.today()
    if isinstance(value, date):
        return value

    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise PaymentInputError("To'lov sanasi YYYY-MM-DD formatida bo'lishi kerak.")


def next_month(value):
    if value.month == 12:
        return date(value.year + 1, 1, 1)
    return date(value.year, value.month + 1, 1)


def parse_money(value, field_name='amount'):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
       raise PaymentInputError(
    f"{field_name} noto'g'ri son bo'lishi kerak."
)

    amount = amount.quantize(Decimal('0.01'))
    if amount < 0:
        raise PaymentInputError(f'{field_name} 0 dan kichik bo\'lishi mumkin emas.')
    if amount > Decimal('1000000000'):
        raise PaymentInputError(f'{field_name} juda katta qiymat.')
    return amount


def assert_admin_user(user):
    if not hasattr(user, 'is_authenticated') or not hasattr(user, 'is_staff') or not hasattr(user, 'is_admin_role'):
        raise PermissionDenied('Foydalanuvchi obyektida kerakli atributlar yo\'q.')
    if not user.is_authenticated:
        raise PermissionDenied('Login talab qilinadi.')
    if not user.is_staff and not user.is_admin_role:
        raise PermissionDenied('Faqat admin to\'lov qabul qila oladi.')


def get_payment_group(group_id):
    return get_object_or_404(Group.objects.filter(is_active=True), pk=group_id)


def get_payment_student(student_id, group):
    student = get_object_or_404(Student.objects.filter(is_active=True), pk=student_id)
    is_group_student = group.groupstudent_set.filter(student=student, is_active=True).exists()
    if not is_group_student:
        raise PaymentInputError("O'quvchi ushbu guruhga biriktirilmagan.")
    return student


def get_or_create_month_balance(student, group, month):
    # Guruh tekin bo'lsa ham uning uchun balans yaratilishiga ruxsat beramiz.
    if group.monthly_fee < 0:
        raise PaymentInputError("Guruh oylik to'lovi 0 dan past bo'lishi mumkin emas.")

    balance, _ = StudentMonthBalance.objects.select_for_update().get_or_create(
        student=student,
        group=group,
        month=month,
        defaults={'required_amount': group.monthly_fee},
    )

    if balance.required_amount != group.monthly_fee and balance.paid_amount == 0:
        balance.required_amount = group.monthly_fee
        balance.full_clean()
        balance.save()

    return balance


def serialize_money(value):
    value = Decimal(value).quantize(Decimal('0.01'))
    return str(value.quantize(Decimal('1')) if value == value.to_integral() else value)


def serialize_balance(balance):
    return {
        'id': balance.id,
        'month': balance.month.isoformat(),
        'required_amount': serialize_money(balance.required_amount),
        'paid_amount': serialize_money(balance.paid_amount),
        'debt_amount': serialize_money(balance.debt_amount),
        'advance_amount': serialize_money(balance.advance_amount),
        'status': balance.status,
        'status_label': balance.get_status_display(),
    }


def build_payment_summary(allocations, payment_month):
    current_month_status = None
    closed_months_count = 0
    advance_amount = Decimal('0')
    debt_amount = Decimal('0')

    for balance in allocations:
        if balance.status == 'CLOSED':
            closed_months_count += 1

        if balance.month == payment_month:
            current_month_status = balance.status
            debt_amount = balance.debt_amount

        if balance.month > payment_month and balance.status != 'CLOSED':
            advance_amount += balance.paid_amount

    return {
        'current_month_status': current_month_status,
        'closed_months_count': closed_months_count,
        'advance_amount': serialize_money(advance_amount),
        'debt_amount': serialize_money(debt_amount),
        'remaining_amount': '0',
    }


def get_student_payment_state(student_id, group_id, from_month=None, months=6):
    group = get_payment_group(group_id)
    student = get_payment_student(student_id, group)
    month = first_day_of_month(from_month or date.today())
    balances = []

    for _ in range(months):
        balance = get_or_create_month_balance(student, group, month)
        balances.append(serialize_balance(balance))
        month = next_month(month)

    return {
        'student': {'id': student.id, 'full_name': str(student)},
        'group': {'id': group.id, 'name': group.name, 'monthly_fee': serialize_money(group.monthly_fee)},
        'balances': balances,
    }


@transaction.atomic
def apply_payment(user, student_id, group_id, amount, payment_date=None, method=PaymentMethod.CASH, note=''):
    assert_admin_user(user)

    group = get_payment_group(group_id)
    student = get_payment_student(student_id, group)
    payment_date = parse_payment_date(payment_date)
    payment_month = first_day_of_month(payment_date)
    amount = parse_money(amount)

    if method not in PaymentMethod.values:
        raise PaymentInputError("To'lov turi noto'g'ri.")

    note_str = str(note or '').strip()
    if len(note_str) > 255:
        raise PaymentInputError("Izoh 255 belgidan oshmasligi kerak.")
    payment = PaymentTransaction.objects.create(
        student=student,
        group=group,
        amount=amount,
        payment_date=payment_date,
        method=method,
        created_by=user,
        note=note_str,
    )

    remaining = amount
    month = payment_month
    allocations = []
    allocated_balances = []

    while remaining > 0:
        balance = get_or_create_month_balance(student, group, month)
        debt = balance.debt_amount

        if debt == 0:
            month = next_month(month)
            continue

        allocated = min(remaining, debt)
        balance.paid_amount += allocated
        balance.full_clean()
        balance.save()

        PaymentAllocation.objects.create(
            payment=payment,
            balance=balance,
            amount=allocated,
        )
        allocations.append(serialize_balance(balance))
        allocated_balances.append(balance)

        remaining -= allocated
        month = next_month(month)

    return {
        'payment': {
            'id': payment.id,
            'amount': serialize_money(payment.amount),
            'payment_date': payment.payment_date.isoformat(),
            'method': payment.method,
        },
        'student': {'id': student.id, 'full_name': str(student)},
        'group': {'id': group.id, 'name': group.name, 'monthly_fee': serialize_money(group.monthly_fee)},
        'allocations': allocations,
        'summary': build_payment_summary(allocated_balances, payment_month),
        'remaining': serialize_money(remaining),
    }
