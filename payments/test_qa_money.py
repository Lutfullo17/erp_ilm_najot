"""QA: pul va ma'lumot yaxlitligi. Har bir test bitta tekshiruvni (yoki ma'lum kamchilikni) hujjatlaydi."""
import datetime
import random
from decimal import Decimal
from unittest import mock

from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone

from groups_app.models import Group, GroupStudent
from payments.billing import current_due_month, effective_fee, period_due_date
from payments.models import PaymentAllocation, PaymentTransaction, StudentMonthBalance
from payments.services import PaymentInputError, apply_payment, delete_payment, parse_money
from students.models import Student
from users1.models import User


def mk(username, role):
    u = User(username=username, role=role)
    u.set_password('x')
    u.save()
    return u


@override_settings(PAYMENT_BACKDATE_DAYS=3650)
class MoneyBase(TestCase):
    def setUp(self):
        self.director = mk('d', 'DIRECTOR')
        self.today = timezone.localdate()
        self.group = Group.objects.create(name='G', monthly_fee=Decimal('300000'), start_date=self.today - datetime.timedelta(days=95))
        self.student = Student.objects.create(first_name='A', last_name='B')
        self.m = GroupStudent.objects.create(group=self.group, student=self.student, joined_at=self.today - datetime.timedelta(days=95))

    def pay(self, amount, **kw):
        return apply_payment(self.director, self.student.pk, self.group.pk, amount, kw.pop('date', None), **kw)

    def assert_invariants(self):
        pair = dict(student=self.student, group=self.group)
        balances = list(StudentMonthBalance.objects.filter(**pair))
        payments_total = sum((p.amount for p in PaymentTransaction.objects.filter(**pair)), Decimal('0'))
        alloc_total = sum((a.amount for a in PaymentAllocation.objects.filter(balance__in=balances)), Decimal('0'))
        self.assertEqual(alloc_total, payments_total, "To'lovlar yig'indisi taqsimot yig'indisiga teng bo'lishi kerak")
        for b in balances:
            allocated = sum((a.amount for a in b.payment_allocations.all()), Decimal('0'))
            self.assertEqual(b.paid_amount, allocated, f'{b.month}: paid_amount taqsimotga mos emas')
            self.assertGreaterEqual(b.paid_amount, 0)
            self.assertGreaterEqual(b.required_amount, 0)
            expected = 'CLOSED' if b.paid_amount >= b.required_amount else ('PARTIAL' if b.paid_amount > 0 else 'OPEN')
            self.assertEqual(b.status, expected)


class AmountParsingTests(MoneyBase):
    def test_invalid_amounts_rejected(self):
        for bad in (0, '0', -1, '-100', 'abc', '', None, 'NaN', 'Infinity', '-Infinity', 10 ** 10, '1000000001'):
            with self.assertRaises(PaymentInputError, msg=repr(bad)):
                self.pay(bad)
        self.assertEqual(PaymentTransaction.objects.count(), 0)

    def test_boundary_amounts(self):
        self.assertEqual(parse_money('0.01'), Decimal('0.01'))
        self.assertEqual(parse_money('1000000000'), Decimal('1000000000.00'))

    def test_extra_decimals_are_rounded_not_rejected(self):
        # Hujjatlangan xulq: 100.555 -> 100.56 (yaxlitlash), rad etilmaydi. so'mda tiyin ma'nosiz, lekin xavfsiz.
        self.assertEqual(parse_money('100.555'), Decimal('100.56'))
        self.assertEqual(parse_money('100.565'), Decimal('100.56'))      # banker yaxlitlash (ROUND_HALF_EVEN)

    def test_scientific_notation_rejected(self):
        # QA-B-07: '1e3' endi aniq xabar bilan rad etiladi.
        with self.assertRaises(PaymentInputError):
            parse_money('1e3')


class DiscountRoundingTests(MoneyBase):
    def test_percentage_discount_rounding_is_cent_exact(self):
        self.group.monthly_fee = Decimal('99999')
        self.group.save()
        self.student.has_discount, self.student.discount_type, self.student.discount_value = True, 'PERCENTAGE', Decimal('12.5')
        self.student.save()
        self.assertEqual(effective_fee(self.student, self.group), Decimal('87499.12'))   # 87499.125 -> half-even

    def test_discount_never_goes_negative(self):
        self.student.has_discount, self.student.discount_type, self.student.discount_value = True, 'FIXED', Decimal('999999')
        self.student.save()
        self.assertEqual(effective_fee(self.student, self.group), Decimal('0.00'))

    def test_free_group_and_zero_fee_payment_goes_to_advance_only(self):
        self.group.monthly_fee = Decimal('0')
        self.group.save()
        self.pay(1000)
        self.assert_invariants()


class InvariantTests(MoneyBase):
    def test_random_operation_sequences_keep_ledger_consistent(self):
        for seed in range(6):
            rnd = random.Random(seed)
            PaymentTransaction.objects.all().delete()
            StudentMonthBalance.objects.all().delete()
            for _ in range(25):
                op = rnd.choice(['pay', 'pay', 'pay', 'delete', 'fee', 'discount', 'leave_join'])
                try:
                    if op == 'pay':
                        d = self.today - datetime.timedelta(days=rnd.randint(0, 90))
                        self.pay(Decimal(rnd.choice([50000, 120000, 300000, 450000, 777777])), date=d)
                    elif op == 'delete' and PaymentTransaction.objects.exists():
                        delete_payment(self.director, PaymentTransaction.objects.order_by('?').first().pk)
                    elif op == 'fee':
                        self.group.monthly_fee = Decimal(rnd.choice([200000, 300000, 400000]))
                        self.group.save()
                    elif op == 'discount':
                        self.student.has_discount = rnd.random() < 0.5
                        self.student.discount_type = rnd.choice(['PERCENTAGE', 'FIXED'])
                        self.student.discount_value = Decimal(rnd.choice([10, 33, 50000]))
                        if self.student.discount_type == 'PERCENTAGE' and self.student.discount_value > 100:
                            self.student.discount_value = Decimal(25)
                        self.student.save()
                    elif op == 'leave_join':
                        m = GroupStudent.objects.get(pk=self.m.pk)
                        m.is_active = not m.is_active
                        m.save()
                except PaymentInputError:
                    pass
                self.assert_invariants()

    def test_delete_payment_restores_exact_previous_state(self):
        self.pay(100000)
        before = list(StudentMonthBalance.objects.values_list('month', 'required_amount', 'paid_amount'))
        p = PaymentTransaction.objects.get(amount=Decimal('250000.00')) if False else None
        r = self.pay(250000)
        delete_payment(self.director, r['payment']['id'])
        after = list(StudentMonthBalance.objects.values_list('month', 'required_amount', 'paid_amount'))
        self.assertEqual(before, after)
        self.assert_invariants()

    def test_payments_order_independent_of_insertion_order(self):
        # Eng eski qarz birinchi yopiladi: sana bo'yicha taqsimlanadi, kiritilish tartibi bo'yicha emas
        self.pay(300000, date=self.today)
        self.pay(300000, date=self.today - datetime.timedelta(days=60))
        first = list(StudentMonthBalance.objects.order_by('month').values_list('month', 'paid_amount'))
        PaymentTransaction.objects.all().delete()
        StudentMonthBalance.objects.all().delete()
        self.pay(300000, date=self.today - datetime.timedelta(days=60))
        self.pay(300000, date=self.today)
        self.assertEqual(first, list(StudentMonthBalance.objects.order_by('month').values_list('month', 'paid_amount')))


class MembershipRulesTests(MoneyBase):
    def test_student_cannot_join_same_group_twice(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            GroupStudent.objects.create(group=self.group, student=self.student)

    def test_no_group_capacity_concept_documented(self):
        # QA-B-05: guruh sig'imi yo'q — 500 ta o'quvchini qo'shish mumkin (biznes talabi bo'lsa qo'shiladi).
        self.assertFalse(hasattr(Group, 'capacity'))

    def test_left_before_joined_is_not_prevented_by_database(self):
        # QA-B-06: joined_at > left_at ni DB/model cheklamaydi
        m = GroupStudent.objects.get(pk=self.m.pk)
        m.left_at = m.joined_at - datetime.timedelta(days=10)
        m.save()
        self.assertLess(m.left_at, m.joined_at)

    def test_overpayment_by_former_member_rejected_and_debt_payable(self):
        self.m.is_active = False
        self.m.save()
        debt = StudentMonthBalance.objects.debts().filter(student=self.student).first()
        with self.assertRaises(PaymentInputError):
            self.pay(10 ** 8)
        if debt:
            self.pay(debt.debt_amount)
        self.assert_invariants()

    def test_deleted_student_cannot_pay(self):
        StudentMonthBalance.objects.all().delete()
        self.student.is_active, self.student.is_deleted = False, True
        self.student.save()
        with self.assertRaises(Exception):
            self.pay(1000)


class TimezoneTests(MoneyBase):
    def test_default_payment_date_uses_tashkent_not_utc(self):
        utc = datetime.timezone.utc
        # 31-oktyabr 19:30 UTC == 1-noyabr 00:30 Toshkent
        with mock.patch('django.utils.timezone.now', return_value=datetime.datetime(2026, 10, 31, 19, 30, tzinfo=utc)):
            self.assertEqual(timezone.localdate(), datetime.date(2026, 11, 1))
            self.group.start_date = datetime.date(2026, 8, 1)
            self.group.save()
            r = apply_payment(self.director, self.student.pk, self.group.pk, 1000)
        self.assertEqual(r['payment']['payment_date'], '2026-11-01')

    def test_due_dates_on_month_ends(self):
        g = Group(start_date=datetime.date(2026, 1, 31))
        self.assertEqual(period_due_date(g, datetime.date(2026, 2, 1)), datetime.date(2026, 2, 28))
        self.assertEqual(period_due_date(g, datetime.date(2028, 2, 1)), datetime.date(2028, 2, 29))   # kabisa yili
        # 28-fevralda fevral muddati keldi, 27-fevralda hali yo'q
        self.assertEqual(current_due_month(g, datetime.date(2026, 2, 28)), datetime.date(2026, 2, 1))
        self.assertEqual(current_due_month(g, datetime.date(2026, 2, 27)), datetime.date(2026, 1, 1))
        self.assertIsNone(current_due_month(g, datetime.date(2026, 1, 30)))

    def test_year_boundary(self):
        g = Group(start_date=datetime.date(2025, 12, 15))
        self.assertEqual(current_due_month(g, datetime.date(2026, 1, 14)), datetime.date(2025, 12, 1))
        self.assertEqual(current_due_month(g, datetime.date(2026, 1, 15)), datetime.date(2026, 1, 1))


class ReportConsistencyTests(MoneyBase):
    def test_cash_totals_equal_sum_of_payments_and_allocation_split(self):
        from django.test import Client
        self.pay(450000)
        self.pay(100000, date=self.today - datetime.timedelta(days=40))
        d = mk('dir2', 'DIRECTOR')
        d.set_password('pw-12345')
        d.save()
        c = Client()
        c.login(username='dir2', password='pw-12345')
        from django.test import override_settings as ov
        with ov(STORAGES={'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}}):
            r = c.get('/reports/finance/?month=%s' % self.today.strftime('%Y-%m'))
        cash = r.context['cash']
        month_total = sum((p.amount for p in PaymentTransaction.objects.filter(
            payment_date__year=self.today.year, payment_date__month=self.today.month)), Decimal('0'))
        self.assertEqual(cash['total'], month_total)
        self.assertEqual(cash['for_this_month'] + cash['for_past_months'] + cash['for_future_months'], cash['total'])
