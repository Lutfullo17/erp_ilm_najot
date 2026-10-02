"""Production auditida topilgan xatolar uchun regressiya testlari."""
from decimal import Decimal as D

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.utils import timezone

from groups_app.models import Group, GroupStudent
from payments.billing import add_months
from payments.models import PaymentTransaction, StudentMonthBalance
from payments.services import PaymentInputError, apply_payment
from reports.views import FinanceReportView
from students.models import Student


class ProductionAuditRegressionTests(TestCase):
    def setUp(self):
        self.director = get_user_model().objects.create_user(username='dir', password='x', role='DIRECTOR')
        self.today = timezone.localdate()
        self.this_month = self.today.replace(day=1)
        self.start = add_months(self.this_month, -3)
        self.group = Group.objects.create(name='G1', monthly_fee=D('500000'), start_date=self.start)

    def add(self, name, joined=None, group=None, **kw):
        s = Student.objects.create(first_name=name, last_name='X', **kw)
        GroupStudent.objects.create(group=group or self.group, student=s, joined_at=joined or self.start)
        return s

    def pay(self, student, amount, group=None, day=None):
        return apply_payment(self.director, student.id, (group or self.group).id, amount, day or self.today)

    def report(self, month):
        req = RequestFactory().get('/', {'month': month.strftime('%Y-%m')})
        req.user = self.director
        view = FinanceReportView()
        view.setup(req)
        return view.get_context_data()

    def test_non_payer_is_in_report(self):
        payer = self.add('Payer')
        self.add('NonPayer')
        self.pay(payer, '2000000')
        stats = self.report(self.this_month)['month_stats']
        self.assertEqual(stats['total_users'], 2)
        self.assertEqual(stats['expected'], D('1000000'))
        self.assertEqual(stats['debt'], D('500000'))

    def test_late_joiner_billed_from_join_month(self):
        s = self.add('Late', joined=self.this_month)
        self.pay(s, '500000')
        months = list(StudentMonthBalance.objects.filter(student=s).values_list('month', flat=True))
        self.assertEqual(months, [self.this_month])

    def test_cash_is_money_received_in_month(self):
        s = self.add('Debtor')
        self.pay(s, '2000000')
        self.assertEqual(self.report(self.this_month)['cash']['total'], D('2000000'))
        self.assertEqual(self.report(self.start)['cash']['total'], 0)

    def test_full_percentage_discount_can_pay_and_is_never_charged(self):
        s = self.add('Free', has_discount=True, discount_type='PERCENTAGE', discount_value=D('100'))
        self.pay(s, '100000')
        self.assertFalse(StudentMonthBalance.objects.filter(student=s, required_amount__gt=0).exists())

    def test_full_fixed_discount_never_charged(self):
        s = self.add('Free2', has_discount=True, discount_type='FIXED', discount_value=D('600000'))
        self.pay(s, '100000')
        self.assertFalse(StudentMonthBalance.objects.filter(student=s, required_amount__gt=0).exists())

    def test_admin_delete_payment_restores_debt(self):
        s = self.add('Del')
        r = self.pay(s, '500000')
        PaymentTransaction.objects.get(pk=r['payment']['id']).delete()
        self.assertEqual(StudentMonthBalance.objects.get(student=s, month=self.start).paid_amount, 0)

    def test_admin_edit_payment_amount_reallocates(self):
        s = self.add('Edit')
        r = self.pay(s, '500000')
        p = PaymentTransaction.objects.get(pk=r['payment']['id'])
        p.amount = D('1000000')
        p.save()
        paid = sum(StudentMonthBalance.objects.filter(student=s).values_list('paid_amount', flat=True))
        self.assertEqual(paid, D('1000000'))

    def test_former_member_can_pay_old_debt(self):
        s = self.add('Leaver')
        gs = GroupStudent.objects.get(student=s, group=self.group)
        gs.is_active = False
        gs.save()
        debt_before = sum(b.debt_amount for b in StudentMonthBalance.objects.filter(student=s))
        self.assertGreater(debt_before, 0)
        self.pay(s, '500000')
        debt_after = sum(b.debt_amount for b in StudentMonthBalance.objects.filter(student=s))
        self.assertEqual(debt_before - debt_after, D('500000'))

    def test_stranger_cannot_pay_to_group(self):
        s = Student.objects.create(first_name='Stranger', last_name='X')
        with self.assertRaises(PaymentInputError):
            self.pay(s, '500000')

    def test_student_in_two_groups_counted_once(self):
        g2 = Group.objects.create(name='G2', monthly_fee=D('300000'), start_date=self.start)
        s = self.add('Two')
        GroupStudent.objects.create(group=g2, student=s, joined_at=self.start)
        stats = self.report(self.this_month)['month_stats']
        self.assertEqual(stats['total_students'], 1)
        self.assertEqual(stats['total_users'], 2)
