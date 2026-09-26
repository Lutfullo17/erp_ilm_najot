"""Oylik to'lov balanslarini hisoblash mexanizmi.

Asosiy qoida: (o'quvchi, guruh) juftligi uchun barcha StudentMonthBalance va
PaymentAllocation yozuvlari `sync_pair()` tomonidan deterministik tarzda qayta
quriladi. Manba ma'lumotlar:

* GroupStudent.joined_at / left_at — qaysi oylar hisoblanadi;
* BillingPause — muzlatish, guruh pauzasi, guruhdan chiqib-qaytish oraliqlari;
* Group.monthly_fee + o'quvchi chegirmasi — oylik summa;
* PaymentTransaction — to'lovlar (sana bo'yicha eng eski qarzdan boshlab taqsimlanadi).

Muddati o'tgan oylarning summasi (required_amount) saqlanib qoladi — guruh narxi
yoki chegirma o'zgarsa, faqat joriy va kelgusi oylarga ta'sir qiladi.
"""
from calendar import monthrange
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

ZERO = Decimal('0')
CENT = Decimal('0.01')
# Oldindan to'lov kelgusi nechta oyga taqsimlanishi mumkin; qolgani avans bo'lib turadi.
MAX_FUTURE_MONTHS = 36


# ---------------------------------------------------------------- sana yordamchilari

def month_start(value):
    return value.replace(day=1)


def add_months(value, months):
    year = value.year + (value.month - 1 + months) // 12
    month = (value.month - 1 + months) % 12 + 1
    return date(year, month, 1)


def period_due_date(group, month):
    """`month` oyi uchun to'lov davri boshlanadigan sana (guruh boshlangan kun bo'yicha)."""
    if group.start_date:
        day = min(group.start_date.day, monthrange(month.year, month.month)[1])
        return month.replace(day=day)
    return month


def current_due_month(group, as_of):
    """`as_of` sanasida muddati kelgan eng oxirgi oy. Guruh hali boshlanmagan bo'lsa None."""
    if group.start_date and as_of < group.start_date:
        return None
    month = month_start(as_of)
    if period_due_date(group, month) > as_of:
        month = add_months(month, -1)
    if group.start_date and month < month_start(group.start_date):
        return None
    return month


def effective_fee(student, group):
    fee = group.monthly_fee if group.monthly_fee is not None else ZERO
    return student.get_effective_fee(fee).quantize(CENT)


# ---------------------------------------------------------------- qaysi oylar hisoblanadi

def _load_pauses(student, group):
    from .models import BillingPause
    return list(BillingPause.objects.filter(
        (Q(student=student) & Q(group__isnull=True))
        | (Q(group=group) & Q(student__isnull=True))
        | (Q(student=student) & Q(group=group))
    ))


def _pause_for(month, due, pauses):
    """Shu oyni qamrab olgan pauza (bo'lmasa None). Pauza tugagan oy hisoblanadi."""
    for p in pauses:
        if p.start_date <= due and (p.end_date is None or month < month_start(p.end_date)):
            return p
    return None


def _is_billable(membership, group, month, pauses):
    due = period_due_date(group, month)
    if month < month_start(membership.joined_at):
        return False
    if group.start_date and month < month_start(group.start_date):
        return False
    if membership.left_at and due >= membership.left_at:
        return False
    return _pause_for(month, due, pauses) is None


def billable_months(membership, group, pauses, as_of, existing_months=()):
    """Muddati kelgan va hisoblanadigan oylar ro'yxati."""
    last = current_due_month(group, as_of)
    if last is None:
        return []
    # Guruh yopilgan yoki a'zolik chiqish sanasisiz o'chirilgan (eski ma'lumot) bo'lsa —
    # yangi oy qo'shilmaydi, faqat mavjudlari qoladi.
    frozen_membership = (
        not group.is_active
        or not membership.student.is_active
        or (not membership.is_active and membership.left_at is None)
    )
    if frozen_membership:
        if not existing_months:
            return []
        last = min(last, max(existing_months))

    first = month_start(membership.joined_at)
    if group.start_date:
        first = max(first, month_start(group.start_date))

    months = []
    month = first
    while month <= last:
        if _is_billable(membership, group, month, pauses):
            months.append(month)
        month = add_months(month, 1)
    return months


def _future_months(membership, group, pauses, after, as_of):
    """Oldindan to'lov uchun kelgusi oylar generatori (ochiq pauza yoki chiqish bo'lsa to'xtaydi)."""
    if membership is None or not membership.is_active or membership.left_at or not group.is_active:
        return
    cur = current_due_month(group, as_of)
    candidates = [month_start(membership.joined_at)]
    if group.start_date:
        candidates.append(month_start(group.start_date))
    if cur is not None:
        candidates.append(add_months(cur, 1))
    if after is not None:
        candidates.append(add_months(after, 1))
    month = max(candidates)
    produced = 0
    while produced < MAX_FUTURE_MONTHS:
        due = period_due_date(group, month)
        pause = _pause_for(month, due, pauses)
        if pause is not None:
            if pause.end_date is None:
                return  # muddatsiz pauza (muzlatish) — avans kutib turadi
            month = add_months(month, 1)
            continue
        yield month
        produced += 1
        month = add_months(month, 1)


# ---------------------------------------------------------------- qayta qurish

@dataclass
class _Slot:
    month: date
    required: Decimal
    paid: Decimal = ZERO
    allocations: list = field(default_factory=list)  # [(payment, amount)]

    @property
    def room(self):
        return self.required - self.paid


@dataclass
class SyncResult:
    student_id: int
    group_id: int
    debt_before: Decimal = ZERO
    debt_after: Decimal = ZERO
    created: int = 0
    updated: int = 0
    deleted: int = 0
    allocations_changed: bool = False

    @property
    def changed(self):
        return bool(self.created or self.updated or self.deleted or self.allocations_changed)


def _debt(balances, as_of):
    return sum(
        (b.required_amount - b.paid_amount for b in balances
         if b.paid_amount < b.required_amount and (b.due_date or b.month) <= as_of),
        ZERO,
    )


@transaction.atomic
def sync_pair(student, group, as_of=None, reprice_past=False):
    """(o'quvchi, guruh) uchun oylik balanslar va to'lov taqsimotini qayta quradi."""
    from groups_app.models import GroupStudent
    from .models import PaymentAllocation, PaymentTransaction, StudentMonthBalance

    as_of = as_of or timezone.localdate()
    membership = (
        GroupStudent.objects.select_for_update()
        .select_related('student', 'group')
        .filter(student=student, group=group).first()
    )
    if membership is not None:
        student, group = membership.student, membership.group

    existing = {
        b.month: b for b in StudentMonthBalance.objects.select_for_update().filter(student=student, group=group)
    }
    payments = list(
        PaymentTransaction.objects.filter(student=student, group=group).order_by('payment_date', 'created_at', 'id')
    )
    result = SyncResult(student.id, group.id, debt_before=_debt(existing.values(), as_of))

    fee = effective_fee(student, group)
    cur = current_due_month(group, as_of)
    pauses = _load_pauses(student, group)

    if membership is not None:
        due_months = billable_months(membership, group, pauses, as_of, tuple(existing))
    else:
        # A'zolik yozuvi yo'q — faqat mavjud muddati kelgan oylar saqlanadi.
        due_months = sorted(m for m in existing if cur is not None and m <= cur)

    def required_for(month):
        old = existing.get(month)
        is_past = cur is not None and month < cur
        if old is not None and is_past and old.required_amount > 0 and not reprice_past:
            return old.required_amount  # o'tgan oy narxi "muzlatilgan"
        return fee

    slots = [_Slot(m, required_for(m)) for m in due_months]
    future = _future_months(membership, group, pauses, due_months[-1] if due_months else None, as_of)

    # To'lovlarni eng eski qarzdan boshlab taqsimlash (FIFO)
    idx = 0
    for payment in payments:
        remaining = payment.amount
        while remaining > 0:
            while idx < len(slots) and slots[idx].room <= 0:
                idx += 1
            if idx == len(slots):
                next_month = next(future, None) if fee > 0 else None
                if next_month is not None:
                    slots.append(_Slot(next_month, fee))
                    continue
                # Joy qolmadi: ortiqcha summa oxirgi oyda avans (ortiqcha to'lov) sifatida turadi.
                if not slots:
                    anchor = add_months(cur, 1) if cur else month_start(group.start_date or payment.payment_date)
                    slots.append(_Slot(anchor, ZERO))
                target = slots[-1]
                amount = remaining
            else:
                target = slots[idx]
                amount = min(remaining, target.room)
            target.paid += amount
            target.allocations.append((payment, amount))
            remaining -= amount

    # --- Bazaga yozish (faqat o'zgargan qatorlar)
    old_alloc = sorted(
        (a.payment_id, a.balance.month, a.amount)
        for a in PaymentAllocation.objects.filter(balance__student=student, balance__group=group).select_related('balance')
    )
    new_alloc = sorted((p.id, s.month, amt) for s in slots for p, amt in s.allocations)
    result.allocations_changed = old_alloc != new_alloc
    if result.allocations_changed:
        PaymentAllocation.objects.filter(balance__student=student, balance__group=group).delete()

    keep = {s.month for s in slots}
    for month, balance in existing.items():
        if month not in keep:
            balance.delete()
            result.deleted += 1

    final = []
    for slot in slots:
        due = period_due_date(group, slot.month)
        balance = existing.get(slot.month)
        if balance is None:
            balance = StudentMonthBalance(student=student, group=group, month=slot.month)
            result.created += 1
        elif (balance.required_amount, balance.paid_amount, balance.due_date) != (slot.required, slot.paid, due):
            result.updated += 1
        else:
            final.append((balance, slot))
            continue
        balance.required_amount = slot.required
        balance.paid_amount = slot.paid
        balance.due_date = due
        balance.save()
        final.append((balance, slot))

    if result.allocations_changed:
        PaymentAllocation.objects.bulk_create([
            PaymentAllocation(payment=p, balance=balance, amount=amt)
            for balance, slot in final for p, amt in slot.allocations
        ])

    result.debt_after = _debt([b for b, _ in final], as_of)
    return result


# ---------------------------------------------------------------- ommaviy chaqiruvlar

def pairs_for_student(student):
    from groups_app.models import GroupStudent
    from .models import StudentMonthBalance
    ids = set(GroupStudent.objects.filter(student=student).values_list('group_id', flat=True))
    ids |= set(StudentMonthBalance.objects.filter(student=student).values_list('group_id', flat=True))
    return ids


def sync_student(student, **kwargs):
    from groups_app.models import Group
    return [sync_pair(student, g, **kwargs) for g in Group.objects.filter(pk__in=pairs_for_student(student))]


def sync_group(group, **kwargs):
    from groups_app.models import GroupStudent
    from students.models import Student
    from .models import StudentMonthBalance
    ids = set(GroupStudent.objects.filter(group=group).values_list('student_id', flat=True))
    ids |= set(StudentMonthBalance.objects.filter(group=group).values_list('student_id', flat=True))
    return [sync_pair(s, group, **kwargs) for s in Student.objects.filter(pk__in=ids)]


def all_pairs():
    from groups_app.models import GroupStudent
    from .models import PaymentTransaction, StudentMonthBalance
    pairs = set(GroupStudent.objects.values_list('student_id', 'group_id'))
    pairs |= set(StudentMonthBalance.objects.values_list('student_id', 'group_id'))
    pairs |= set(PaymentTransaction.objects.values_list('student_id', 'group_id'))
    return sorted(pairs)


def sync_all(active_only=False, **kwargs):
    """Barcha juftliklarni qayta hisoblaydi. active_only=True — faqat faol a'zoliklar (kunlik job)."""
    from groups_app.models import Group, GroupStudent
    from students.models import Student
    if active_only:
        pairs = GroupStudent.objects.filter(
            is_active=True, student__is_active=True, group__is_active=True,
        ).values_list('student_id', 'group_id')
    else:
        pairs = all_pairs()
    students = Student.objects.in_bulk({s for s, _ in pairs})
    groups = Group.objects.in_bulk({g for _, g in pairs})
    return [sync_pair(students[s], groups[g], **kwargs) for s, g in pairs]
