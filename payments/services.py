from datetime import date
from decimal import Decimal, InvalidOperation

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404

from groups_app.models import Group
from students.models import Student

from bot.notifications import notify_payment_received, notify_payment_deleted
from .models import (
    MonthBalanceStatus,
    PaymentAllocation,
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


def add_months(value, months):
    year = value.year + (value.month - 1 + months) // 12
    month = (value.month - 1 + months) % 12 + 1
    return date(year, month, 1)


def get_group_start_month(group):
    if getattr(group, 'start_date', None):
        return first_day_of_month(group.start_date)
    return first_day_of_month(date.today())


def get_current_due_month(group, as_of_date=None):
    as_of_date = as_of_date or date.today()
    if not getattr(group, 'start_date', None):
        return first_day_of_month(as_of_date)

    start_date = group.start_date
    if as_of_date < start_date:
        return None

    months_since_start = (as_of_date.year - start_date.year) * 12 + (as_of_date.month - start_date.month)
    if as_of_date.day < start_date.day:
        months_since_start -= 1

    if months_since_start < 0:
        return None

    return add_months(first_day_of_month(start_date), months_since_start)


def get_due_months(group, as_of_date=None):
    current_due_month = get_current_due_month(group, as_of_date)
    if current_due_month is None:
        return []

    months = []
    month = get_group_start_month(group)
    while month <= current_due_month:
        months.append(month)
        month = next_month(month)
    return months


def get_or_create_advance_balance(student, group, month, lock=False):
    qs = StudentMonthBalance.objects.all()
    if lock:
        qs = qs.select_for_update()

    balance, _ = qs.get_or_create(
        student=student,
        group=group,
        month=month,
        defaults={'required_amount': 0, 'paid_amount': 0},
    )
    return balance


def ensure_due_balances(student, group, as_of_date=None):
    due_months = get_due_months(group, as_of_date)
    effective_fee = student.get_effective_fee(group.monthly_fee)
    balances = []
    for month in due_months:
        balance = get_or_create_month_balance(student, group, month)
        if balance.required_amount == 0:
            balance.required_amount = effective_fee
            balance.full_clean()
            balance.save()
        balances.append(balance)
    return balances


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
    if not hasattr(user, 'is_authenticated') or not hasattr(user, 'is_admin_access'):
        raise PermissionDenied('Foydalanuvchi obyektida kerakli atributlar yo\'q.')
    if not user.is_authenticated:
        raise PermissionDenied('Login talab qilinadi.')
    if not user.is_admin_access:
        raise PermissionDenied('Faqat admin yoki director to\'lov qabul qila oladi.')


def get_payment_group(group_id):
    return get_object_or_404(Group.objects.filter(is_active=True), pk=group_id)


def get_payment_student(student_id, group):
    student = get_object_or_404(Student.objects.filter(is_active=True), pk=student_id)
    is_group_student = group.groupstudent_set.filter(student=student, is_active=True).exists()
    if not is_group_student:
        raise PaymentInputError("O'quvchi ushbu guruhga biriktirilmagan.")
    return student


def get_or_create_month_balance(student, group, month, lock=False):
    # Guruh tekin bo'lsa ham uning uchun balans yaratilishiga ruxsat beramiz.
    if group.monthly_fee < 0:
        raise PaymentInputError("Guruh oylik to'lovi 0 dan past bo'lishi mumkin emas.")

    # Chegirma hisobga olingan to'lov
    effective_fee = student.get_effective_fee(group.monthly_fee)

    qs = StudentMonthBalance.objects.all()
    if lock:
        qs = qs.select_for_update()

    balance, created = qs.get_or_create(
        student=student,
        group=group,
        month=month,
        defaults={'required_amount': effective_fee},
    )

    # Yangi yaratilgan balanslar uchun chegirma qo'llanadi
    # Eski to'langan balanslarni o'zgartirmaymiz
    if not created and balance.required_amount != effective_fee and balance.paid_amount == 0:
        balance.required_amount = effective_fee
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
        if balance.status == MonthBalanceStatus.CLOSED:
            closed_months_count += 1

        if balance.month == payment_month:
            current_month_status = balance.status
            debt_amount = balance.debt_amount

        if balance.advance_amount > 0:
            advance_amount += balance.advance_amount

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
    today = date.today()
    start_month = first_day_of_month(from_month or get_group_start_month(group))

    if from_month is not None and getattr(group, 'start_date', None):
        start_month = max(start_month, get_group_start_month(group))

    current_due_month = get_current_due_month(group, today)
    if current_due_month is not None:
        end_month = add_months(start_month, max(0, months - 1))
        if end_month > current_due_month:
            end_month = current_due_month
        ensure_due_balances(student, group, today)
    else:
        end_month = add_months(start_month, max(0, months - 1))

    balances_qs = StudentMonthBalance.objects.filter(
        student=student,
        group=group,
        month__range=(start_month, end_month),
    ).order_by('month')

    balances = [serialize_balance(balance) for balance in balances_qs]

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

    payment_month = max(payment_month, get_group_start_month(group))
    current_due_month = get_current_due_month(group, payment_date)
    if current_due_month is not None:
        ensure_due_balances(student, group, payment_date)

    earliest_debt = StudentMonthBalance.objects.filter(
        student=student,
        group=group,
        status__in=[MonthBalanceStatus.OPEN, MonthBalanceStatus.PARTIAL]
    ).order_by('month').first()

    if earliest_debt:
        current_month = earliest_debt.month
    elif current_due_month is not None and get_group_start_month(group) <= current_due_month:
        current_month = get_group_start_month(group)
    else:
        current_month = payment_month

    remaining = amount
    allocations = []
    allocated_balances = []

    limit = 24
    while remaining > 0 and limit > 0:
        is_due_month = current_due_month is not None and current_month <= current_due_month

        if is_due_month:
            balance = get_or_create_month_balance(student, group, current_month, lock=True)
        elif remaining < group.monthly_fee:
            balance = get_or_create_advance_balance(student, group, current_month, lock=True)
        else:
            balance = get_or_create_month_balance(student, group, current_month, lock=True)

        if balance.required_amount == 0:
            if is_due_month or remaining >= group.monthly_fee:
                balance.required_amount = group.monthly_fee
                balance.full_clean()
                balance.save()
            else:
                balance.paid_amount += remaining
                balance.save()

                PaymentAllocation.objects.create(
                    payment=payment,
                    balance=balance,
                    amount=remaining,
                )
                allocations.append(serialize_balance(balance))
                allocated_balances.append(balance)
                remaining = Decimal('0')
                break

        debt = balance.debt_amount
        if debt <= 0:
            current_month = next_month(current_month)
            limit -= 1
            continue

        allocated = min(remaining, debt)
        balance.paid_amount += allocated
        balance.save()

        PaymentAllocation.objects.create(
            payment=payment,
            balance=balance,
            amount=allocated,
        )
        allocations.append(serialize_balance(balance))
        allocated_balances.append(balance)

        remaining -= allocated

        if allocated < debt:
            break

        current_month = next_month(current_month)
        limit -= 1

    if remaining > 0 and current_month > (current_due_month or date.min) and remaining < group.monthly_fee:
        advance_balance = get_or_create_advance_balance(student, group, current_month, lock=True)
        advance_balance.paid_amount += remaining
        advance_balance.save()

        PaymentAllocation.objects.create(
            payment=payment,
            balance=advance_balance,
            amount=remaining,
        )
        allocations.append(serialize_balance(advance_balance))
        allocated_balances.append(advance_balance)
        remaining = Decimal('0')

    try:
        notify_payment_received(payment)
    except Exception:
        pass

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


@transaction.atomic
def delete_payment(user, payment_id):
    if not user.is_director:
        raise PermissionDenied("Faqat direktor to'lovlarni o'chira oladi.")
    
    payment = get_object_or_404(PaymentTransaction, pk=payment_id)
    
    # Revert allocations
    allocations = payment.allocations.all().select_for_update()
    for allocation in allocations:
        balance = allocation.balance
        balance.paid_amount -= allocation.amount
        balance.save() # Status will be refreshed in save/signal if implemented
        
    # Telegram notification
    try:
        notify_payment_deleted(payment)
    except:
        pass

    payment.delete()
    return True
