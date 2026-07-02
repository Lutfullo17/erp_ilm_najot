from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from groups_app.models import Group, GroupStudent
from payments.models import StudentMonthBalance, MonthBalanceStatus
from payments.services import apply_payment, get_student_payment_state
from students.models import Student

User = get_user_model()


class PaymentBusinessLogicTestCase(TestCase):
    @staticmethod
    def add_months(value, months):
        year = value.year + (value.month - 1 + months) // 12
        month = (value.month - 1 + months) % 12 + 1
        return date(year, month, 1)

    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin',
            password='password',
            role=User.Role.ADMINISTRATOR,
        )

        self.student = Student.objects.create(
            first_name='Test',
            last_name='Student',
            phone='1234567890',
            is_active=True,
        )

        self.group = Group.objects.create(
            name='Test Group',
            monthly_fee=Decimal('200000'),
            start_date=date(2026, 7, 5),
            is_active=True,
        )

        GroupStudent.objects.create(
            student=self.student,
            group=self.group,
            is_active=True,
        )

    def test_get_student_payment_state_creates_only_current_due_month(self):
        today = date.today()
        start_date = date(today.year, today.month, 5)
        if start_date > today:
            prev_month = today.month - 1 or 12
            prev_year = today.year - 1 if today.month == 1 else today.year
            start_date = date(prev_year, prev_month, 5)

        self.group.start_date = start_date
        self.group.save()

        response = get_student_payment_state(self.student.id, self.group.id)

        expected_month = start_date.replace(day=1).isoformat()
        self.assertEqual(len(response['balances']), 1)
        self.assertEqual(response['balances'][0]['month'], expected_month)
        self.assertEqual(response['balances'][0]['status'], MonthBalanceStatus.OPEN)
        self.assertEqual(StudentMonthBalance.objects.filter(student=self.student, group=self.group).count(), 1)

    def test_apply_payment_closes_oldest_due_and_keeps_future_month_open(self):
        today = date.today()
        start_date = date(today.year, today.month, 5)
        if start_date > today:
            prev_month = today.month - 1 or 12
            prev_year = today.year - 1 if today.month == 1 else today.year
            start_date = date(prev_year, prev_month, 5)

        self.group.start_date = start_date
        self.group.save()

        payment_date = start_date + timedelta(days=35)

        result = apply_payment(
            self.admin,
            self.student.id,
            self.group.id,
            '200000',
            payment_date=payment_date.isoformat(),
        )

        self.assertEqual(result['remaining'], '0')
        balances = StudentMonthBalance.objects.filter(student=self.student, group=self.group).order_by('month')
        self.assertEqual(balances.count(), 2)
        self.assertEqual(balances[0].month, start_date.replace(day=1))
        self.assertEqual(balances[0].status, MonthBalanceStatus.CLOSED)
        self.assertEqual(balances[1].month, self.add_months(start_date.replace(day=1), 1))
        self.assertEqual(balances[1].status, MonthBalanceStatus.OPEN)
        self.assertEqual(balances[1].debt_amount, Decimal('200000'))

    def test_overpayment_stores_advance_without_creating_future_debt(self):
        today = date.today()
        start_date = date(today.year, today.month, 5)
        if start_date > today:
            prev_month = today.month - 1 or 12
            prev_year = today.year - 1 if today.month == 1 else today.year
            start_date = date(prev_year, prev_month, 5)

        self.group.start_date = start_date
        self.group.save()

        payment_date = start_date + timedelta(days=15)
        result = apply_payment(
            self.admin,
            self.student.id,
            self.group.id,
            '450000',
            payment_date=payment_date.isoformat(),
        )

        self.assertEqual(result['remaining'], '0')
        first_month = StudentMonthBalance.objects.get(student=self.student, group=self.group, month=start_date.replace(day=1))
        second_month = StudentMonthBalance.objects.get(student=self.student, group=self.group, month=self.add_months(start_date.replace(day=1), 1))
        advance_month = StudentMonthBalance.objects.get(student=self.student, group=self.group, month=self.add_months(start_date.replace(day=1), 2))

        self.assertEqual(first_month.status, MonthBalanceStatus.CLOSED)
        self.assertEqual(second_month.status, MonthBalanceStatus.CLOSED)
        self.assertEqual(second_month.debt_amount, Decimal('0'))
        self.assertEqual(advance_month.required_amount, Decimal('0'))
        self.assertEqual(advance_month.paid_amount, Decimal('50000.00'))
        self.assertEqual(advance_month.advance_amount, Decimal('50000.00'))

    def test_partial_payment_marks_current_period_partial(self):
        today = date.today()
        start_date = date(today.year, today.month, 5)
        if start_date > today:
            prev_month = today.month - 1 or 12
            prev_year = today.year - 1 if today.month == 1 else today.year
            start_date = date(prev_year, prev_month, 5)

        self.group.start_date = start_date
        self.group.save()

        payment_date = start_date + timedelta(days=15)
        result = apply_payment(
            self.admin,
            self.student.id,
            self.group.id,
            '120000',
            payment_date=payment_date.isoformat(),
        )

        self.assertEqual(result['remaining'], '0')
        balance = StudentMonthBalance.objects.get(student=self.student, group=self.group, month=start_date.replace(day=1))
        self.assertEqual(balance.status, MonthBalanceStatus.PARTIAL)
        self.assertEqual(balance.debt_amount, Decimal('80000.00'))
        self.assertEqual(balance.advance_amount, Decimal('0.00'))
