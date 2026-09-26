"""Oylik to'lov hisob-kitobi va moliyaviy hisobot uchun regressiya testlari.

Har bir test production'da topilgan aniq muammoni tekshiradi.
"""
import re
from datetime import date
from decimal import Decimal
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db.models import Sum
from django.test import TestCase, override_settings

from groups_app.models import Group, GroupStudent
from payments.billing import current_due_month, period_due_date, sync_all, sync_pair
from payments.models import BillingPause, PaymentAllocation, PaymentTransaction, StudentMonthBalance
from payments.services import PaymentInputError, apply_payment, delete_payment, get_student_payment_state
from students.models import Student

User = get_user_model()
D = Decimal
STATIC = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}


@override_settings(STORAGES=STATIC)
class BillingTestCase(TestCase):
    TODAY = date(2026, 8, 20)

    def setUp(self):
        patcher = mock.patch('django.utils.timezone.localdate', return_value=self.TODAY)
        self.clock = patcher.start()
        self.addCleanup(patcher.stop)
        self.director = User.objects.create_user('dir', password='x', role=User.Role.DIRECTOR)
        self.teacher = User.objects.create_user('t', password='x', role=User.Role.TEACHER,
                                                first_name='Aziz', last_name='Karimov')
        self.group = Group.objects.create(name='G1', monthly_fee=D('500000'), teacher=self.teacher,
                                          start_date=date(2026, 6, 1))

    # ---------------------------------------------------------- yordamchilar
    def set_today(self, value):
        self.clock.return_value = value

    def student(self, name, joined=date(2026, 6, 1), group=None, **kw):
        s = Student.objects.create(first_name=name, last_name='X', **kw)
        GroupStudent.objects.create(group=group or self.group, student=s, joined_at=joined)
        return s

    def pay(self, s, amount, d, group=None):
        return apply_payment(self.director, s.id, (group or self.group).id, amount, d)

    def balances(self, s, group=None):
        return [
            (b.month.strftime('%Y-%m'), int(b.required_amount), int(b.paid_amount))
            for b in StudentMonthBalance.objects.filter(student=s, group=group or self.group).order_by('month')
        ]

    def report(self, month):
        self.client.force_login(self.director)
        response = self.client.get('/reports/finance/', {'month': month})
        self.assertEqual(response.status_code, 200)
        return response

    def assert_allocations_consistent(self):
        for p in PaymentTransaction.objects.all():
            self.assertEqual(p.allocations.aggregate(s=Sum('amount'))['s'], p.amount, f'payment {p.id}')
        for b in StudentMonthBalance.objects.all():
            self.assertEqual(b.payment_allocations.aggregate(s=Sum('amount'))['s'] or 0, b.paid_amount, str(b))

    def tearDown(self):
        self.assert_allocations_consistent()


class MembershipDatesTests(BillingTestCase):
    def test_new_student_is_billed_from_join_month_not_group_start(self):
        vali = self.student('Vali', joined=date(2026, 8, 10))
        self.pay(vali, 500000, '2026-08-10')
        self.assertEqual(self.balances(vali), [('2026-08', 500000, 500000)])
        self.assertFalse(vali.has_debt)

    def test_balances_created_on_join_so_unpaid_students_are_visible(self):
        ali, soli, guli = self.student('Ali'), self.student('Soli'), self.student('Guli')
        self.pay(ali, 1500000, '2026-08-05')
        stats = self.report('2026-08').context['month_stats']
        self.assertEqual(stats['total_users'], 3)
        self.assertEqual(stats['expected'], D('1500000'))
        self.assertEqual(stats['collected'], D('500000'))
        self.assertEqual(stats['debt'], D('1000000'))
        self.assertEqual((stats['paid_users'], stats['unpaid_users']), (1, 2))

    def test_daily_job_creates_new_month_for_everyone(self):
        ali = self.student('Ali')
        self.set_today(date(2026, 9, 1))
        sync_all(active_only=True)
        self.assertEqual(self.balances(ali)[-1], ('2026-09', 500000, 0))

    def test_left_student_not_billed_after_leaving_and_debt_shown_separately(self):
        ali = self.student('Ali')
        gs = GroupStudent.objects.get(student=ali)
        gs.is_active = False
        gs.save()
        gs.refresh_from_db()
        self.assertEqual(gs.left_at, self.TODAY)
        self.set_today(date(2026, 10, 5))
        sync_all()
        self.assertEqual([m for m, _, _ in self.balances(ali)], ['2026-06', '2026-07', '2026-08'])
        overall = self.report('2026-10').context['overall']
        self.assertEqual(overall['debt'], 0)
        self.assertEqual(overall['former_debt'], D('1500000'))

    def test_rejoin_skips_months_in_between(self):
        ali = self.student('Ali')
        self.pay(ali, 1500000, '2026-08-01')
        gs = GroupStudent.objects.get(student=ali)
        gs.is_active = False
        gs.save()                                   # 20-avgust chiqdi
        self.set_today(date(2026, 10, 5))
        gs.is_active = True
        gs.save()                                   # 5-oktabr qaytdi
        self.assertEqual([m for m, _, _ in self.balances(ali)], ['2026-06', '2026-07', '2026-08', '2026-10'])

    def test_student_left_status_removes_from_groups(self):
        ali = self.student('Ali')
        ali.status = Student.Status.LEFT
        ali.save()
        self.assertFalse(GroupStudent.objects.get(student=ali).is_active)
        self.set_today(date(2026, 9, 10))
        sync_all()
        self.assertEqual(len(self.balances(ali)), 3)

    def test_frozen_student_not_billed_until_unfrozen(self):
        ali = self.student('Ali')
        ali.status = Student.Status.FROZEN
        ali.save()
        self.set_today(date(2026, 10, 10))
        sync_all()
        self.assertEqual(len(self.balances(ali)), 3)   # sentyabr, oktabr hisoblanmadi
        self.set_today(date(2026, 11, 2))
        ali.status = Student.Status.ACTIVE
        ali.save()
        self.assertEqual([m for m, _, _ in self.balances(ali)][-2:], ['2026-08', '2026-11'])

    def test_paused_group_not_billed(self):
        ali = self.student('Ali')
        self.group.is_paused = True
        self.group.save()
        self.set_today(date(2026, 9, 15))
        sync_all()
        self.assertEqual(self.balances(ali)[-1][0], '2026-08')
        self.assertTrue(BillingPause.objects.filter(group=self.group, end_date__isnull=True).exists())


class FeeAndDiscountTests(BillingTestCase):
    def test_discount_kept_for_prepaid_months(self):
        s = self.student('Chegirma', has_discount=True, discount_type='PERCENTAGE', discount_value=D('50'))
        self.pay(s, 1250000, '2026-08-05')
        self.pay(s, 500000, '2026-08-06')
        self.assertTrue(all(req == 250000 for _, req, _ in self.balances(s)))
        self.assertEqual(self.balances(s)[-1], ('2026-12', 250000, 250000))

    def test_fee_change_does_not_touch_past_months(self):
        ali = self.student('Ali')
        self.pay(ali, 250000, '2026-06-03')
        self.group.monthly_fee = D('600000')
        self.group.save()
        self.assertEqual(self.balances(ali), [
            ('2026-06', 500000, 250000), ('2026-07', 500000, 0), ('2026-08', 600000, 0),
        ])

    def test_discount_change_applies_to_current_and_future(self):
        s = self.student('Ali')
        self.pay(s, 2000000, '2026-08-01')      # iyun-avgust + sentyabr avans
        s.has_discount, s.discount_type, s.discount_value = True, 'FIXED', D('100000')
        s.save()
        self.assertEqual(self.balances(s), [
            ('2026-06', 500000, 500000), ('2026-07', 500000, 500000),
            ('2026-08', 400000, 400000), ('2026-09', 400000, 400000), ('2026-10', 400000, 200000),
        ])

    def test_group_without_fee_gives_clear_error(self):
        g = Group.objects.create(name='Narxsiz', monthly_fee=None, start_date=date(2026, 6, 1))
        s = self.student('Ali', group=g)
        with self.assertRaisesMessage(PaymentInputError, "oylik to'lovi kiritilmagan"):
            self.pay(s, 100000, '2026-08-05', group=g)
        self.assertFalse(PaymentTransaction.objects.exists())

    def test_invalid_payments_rejected(self):
        ali = self.student('Ali')
        with self.assertRaises(PaymentInputError):
            self.pay(ali, 100000, '2026-08-21')   # kelajak sana
        with self.assertRaises(PaymentInputError):
            self.pay(ali, 0, '2026-08-05')
        with self.assertRaises(PaymentInputError):
            self.pay(ali, 'NaN', '2026-08-05')


class AdvanceAndDeleteTests(BillingTestCase):
    def test_partial_advance_is_not_debt(self):
        ali = self.student('Ali')
        self.pay(ali, 1700000, '2026-08-05')
        sep = StudentMonthBalance.objects.get(student=ali, month=date(2026, 9, 1))
        self.assertEqual((sep.required_amount, sep.paid_amount), (D('500000'), D('200000')))
        self.assertFalse(sep.is_due)
        self.assertFalse(ali.has_debt)
        self.assertFalse(StudentMonthBalance.objects.debts().exists())
        overall = self.report('2026-08').context['overall']
        self.assertEqual(overall['advance'], D('200000'))
        state = get_student_payment_state(ali.id, self.group.id, months=12)
        self.assertEqual(sum(D(b['debt_amount']) for b in state['balances']), 0)
        self.assertEqual(sum(D(b['advance_amount']) for b in state['balances']), D('200000'))

    def test_delete_payment_reallocates_remaining_payments(self):
        ali = self.student('Ali')
        first = self.pay(ali, 500000, '2026-06-05')
        self.pay(ali, 500000, '2026-07-05')
        delete_payment(self.director, first['payment']['id'])
        self.assertEqual(self.balances(ali), [
            ('2026-06', 500000, 500000), ('2026-07', 500000, 0), ('2026-08', 500000, 0),
        ])

    def test_backdated_payment_goes_to_oldest_debt(self):
        ali = self.student('Ali')
        self.pay(ali, 500000, '2026-08-01')
        self.pay(ali, 500000, '2026-06-10')
        self.assertEqual([p for _, _, p in self.balances(ali)], [500000, 500000, 0])

    def test_sync_is_idempotent(self):
        ali = self.student('Ali')
        self.pay(ali, 1700000, '2026-08-05')
        result = sync_pair(ali, self.group)
        self.assertFalse(result.changed)


class ReportTests(BillingTestCase):
    def test_cash_is_split_by_target_month(self):
        ali = self.student('Ali')
        self.pay(ali, 1700000, '2026-08-05')
        ctx = self.report('2026-08').context
        self.assertEqual(ctx['cash']['total'], D('1700000'))
        self.assertEqual(ctx['cash']['for_this_month'], D('500000'))
        self.assertEqual(ctx['cash']['for_past_months'], D('1000000'))
        self.assertEqual(ctx['cash']['for_future_months'], D('200000'))
        # Iyun hisobotida kassa 0, lekin iyun oyi yopilgan
        june = self.report('2026-06').context
        self.assertEqual(june['cash']['total'], 0)
        self.assertEqual(june['month_stats']['collected'], D('500000'))

    def test_future_month_advance_not_counted_as_paid_or_negative_debt(self):
        ali = self.student('Ali')
        self.pay(ali, 1700000, '2026-08-05')
        ctx = self.report('2026-09').context
        self.assertEqual(ctx['month_stats']['total_users'], 0)
        self.assertEqual(ctx['month_stats']['debt'], 0)
        self.assertEqual(ctx['not_due']['count'], 1)

    def test_overpayment_does_not_make_negative_debt(self):
        g = Group.objects.create(name='Tekin', monthly_fee=D('0'), start_date=date(2026, 8, 1))
        s = self.student('Ali', group=g, joined=date(2026, 8, 1))
        self.pay(s, 100000, '2026-08-05', group=g)
        stats = self.report('2026-08').context['month_stats']
        self.assertEqual(stats['debt'], 0)
        self.assertEqual(stats['collected'], 0)

    def test_template_has_valid_css_widths_and_teacher(self):
        a, b = self.student('Ali'), self.student('Vali')
        self.pay(a, 1500000, '2026-08-02')
        self.pay(b, 1250000, '2026-08-02')
        html = self.report('2026-08').content.decode()
        widths = re.findall(r'style="width: ([^;%]+)%', html)
        self.assertTrue(widths)
        self.assertTrue(all(w.isdigit() for w in widths), widths)
        self.assertIn('Aziz Karimov', html)

    def test_twelve_month_chart_is_calendar_based(self):
        ali = self.student('Ali')
        self.pay(ali, 500000, '2026-06-02')
        self.pay(ali, 1000000, '2026-08-02')
        chart = self.report('2026-08').context['monthly_income']
        self.assertEqual(len(chart), 12)
        self.assertEqual((chart[0]['month'], chart[0]['width']), (date(2026, 8, 1), 100))
        self.assertEqual(chart[1]['total'], 0)                  # iyul — to'lov yo'q
        self.assertEqual(chart[2]['width'], 50)


class DatesTests(BillingTestCase):
    def test_due_date_clamped_to_month_end(self):
        g = Group(name='x', start_date=date(2026, 1, 31))
        self.assertEqual(period_due_date(g, date(2026, 2, 1)), date(2026, 2, 28))
        self.assertEqual(current_due_month(g, date(2026, 2, 28)), date(2026, 2, 1))
        self.assertEqual(current_due_month(g, date(2026, 2, 27)), date(2026, 1, 1))

    def test_mid_month_group_start(self):
        g = Group.objects.create(name='G15', monthly_fee=D('500000'), start_date=date(2026, 6, 15))
        s = self.student('Ali', group=g)
        self.assertEqual([m for m, _, _ in self.balances(s, g)], ['2026-06', '2026-07', '2026-08'])
        self.set_today(date(2026, 9, 10))
        sync_all()
        self.assertEqual(len(self.balances(s, g)), 3)    # sentyabr muddati 15-da
        self.set_today(date(2026, 9, 15))
        sync_all()
        self.assertEqual(len(self.balances(s, g)), 4)


class LegacyDataTests(BillingTestCase):
    """Eski kod yaratgan noto'g'ri ma'lumotlarni sync_balances buyrug'i tuzatadi."""

    def test_command_fixes_pre_join_balances(self):
        vali = self.student('Vali', joined=date(2026, 8, 10))
        # Eski kod holatini qo'lda yaratamiz: pul iyunga yozilgan, iyul-avgust qarz.
        StudentMonthBalance.objects.filter(student=vali).delete()
        payment = PaymentTransaction(student=vali, group=self.group, amount=D('500000'),
                                     payment_date=date(2026, 8, 10), created_by=self.director)
        payment._skip_sync = True
        payment.save()
        june = StudentMonthBalance.objects.create(student=vali, group=self.group, month=date(2026, 6, 1),
                                                  required_amount=D('500000'), paid_amount=D('500000'))
        for m in (7, 8):
            StudentMonthBalance.objects.create(student=vali, group=self.group, month=date(2026, m, 1),
                                               required_amount=D('500000'))
        PaymentAllocation.objects.create(payment=payment, balance=june, amount=D('500000'))

        out = StringIO()
        call_command('sync_balances', stdout=out)          # dry-run
        self.assertIn('DRY-RUN', out.getvalue())
        self.assertEqual(len(self.balances(vali)), 3)

        call_command('sync_balances', '--apply', stdout=StringIO())
        self.assertEqual(self.balances(vali), [('2026-08', 500000, 500000)])
