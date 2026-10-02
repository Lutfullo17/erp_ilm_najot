from datetime import date
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from groups_app.models import Group, GroupStudent
from payments.models import StudentMonthBalance, MonthBalanceStatus
from payments.services import apply_payment, get_student_payment_state
from students.models import Student

User = get_user_model()


class PaymentBusinessLogicTestCase(TestCase):
    TODAY = date(2026, 8, 20)

    def setUp(self):
        patcher = mock.patch('django.utils.timezone.localdate', return_value=self.TODAY)
        patcher.start()
        self.addCleanup(patcher.stop)

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

        # Guruh 5-iyulda boshlangan: iyul va avgust oylari muddati kelgan.
        self.group = Group.objects.create(
            name='Test Group',
            monthly_fee=Decimal('200000'),
            start_date=date(2026, 7, 5),
            is_active=True,
        )

        GroupStudent.objects.create(
            student=self.student,
            group=self.group,
            joined_at=date(2026, 7, 5),
            is_active=True,
        )

    def balance(self, month):
        return StudentMonthBalance.objects.get(student=self.student, group=self.group, month=month)

    def test_get_student_payment_state_creates_due_months(self):
        response = get_student_payment_state(self.student.id, self.group.id)

        self.assertEqual([b['month'] for b in response['balances']], ['2026-07-01', '2026-08-01'])
        self.assertTrue(all(b['status'] == MonthBalanceStatus.OPEN for b in response['balances']))
        self.assertEqual(self.balance(date(2026, 8, 1)).due_date, date(2026, 8, 5))

    def test_apply_payment_closes_oldest_due_month_first(self):
        result = apply_payment(self.admin, self.student.id, self.group.id, '200000', payment_date='2026-08-10')

        self.assertEqual(result['remaining'], '0')
        self.assertEqual(self.balance(date(2026, 7, 1)).status, MonthBalanceStatus.CLOSED)
        august = self.balance(date(2026, 8, 1))
        self.assertEqual(august.status, MonthBalanceStatus.OPEN)
        self.assertEqual(august.debt_amount, Decimal('200000'))

    def test_overpayment_goes_to_next_month_as_advance_not_debt(self):
        apply_payment(self.admin, self.student.id, self.group.id, '450000', payment_date='2026-08-10')

        september = self.balance(date(2026, 9, 1))
        self.assertEqual(september.required_amount, Decimal('200000'))
        self.assertEqual(september.paid_amount, Decimal('50000.00'))
        self.assertFalse(september.is_due)
        self.assertFalse(StudentMonthBalance.objects.debts().exists())
        self.assertFalse(self.student.has_debt)

    def test_partial_payment_marks_month_partial(self):
        apply_payment(self.admin, self.student.id, self.group.id, '120000', payment_date='2026-08-10')

        july = self.balance(date(2026, 7, 1))
        self.assertEqual(july.status, MonthBalanceStatus.PARTIAL)
        self.assertEqual(july.debt_amount, Decimal('80000.00'))
        self.assertEqual(july.advance_amount, Decimal('0.00'))
