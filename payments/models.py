from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models


class MonthBalanceStatus(models.TextChoices):
    OPEN = 'OPEN', 'Ochiq'
    PARTIAL = 'PARTIAL', 'Qisman'
    CLOSED = 'CLOSED', 'Yopildi'


class PaymentMethod(models.TextChoices):
    CASH = 'CASH', 'Naqd'
    CARD = 'CARD', 'Karta'
    TRANSFER = 'TRANSFER', "O'tkazma"


class StudentMonthBalance(models.Model):
    student = models.ForeignKey(
        'students.Student',
        on_delete=models.PROTECT,
        related_name='month_balances',
    )
    group = models.ForeignKey(
        'groups_app.Group',
        on_delete=models.PROTECT,
        related_name='student_month_balances',
    )
    month = models.DateField()
    required_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0'))],
    )
    paid_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(Decimal('0'))],
    )
    status = models.CharField(
        max_length=20,
        choices=MonthBalanceStatus.choices,
        default=MonthBalanceStatus.OPEN,
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('student', 'group', 'month')
        ordering = ('student__last_name', 'student__first_name', 'month')
        verbose_name = "Oylik balans"
        verbose_name_plural = "Oylik balanslar"

    def __str__(self):
        return f'{self.student} - {self.group} - {self.month:%Y-%m}'

    @property
    def debt_amount(self):
        debt = self.required_amount - self.paid_amount
        return max(debt, Decimal('0'))

    @property
    def advance_amount(self):
        advance = self.paid_amount - self.required_amount
        return max(advance, Decimal('0'))

    def refresh_status(self):
        if self.paid_amount >= self.required_amount:
            self.status = MonthBalanceStatus.CLOSED
        elif self.paid_amount > 0:
            self.status = MonthBalanceStatus.PARTIAL
        else:
            self.status = MonthBalanceStatus.OPEN

    def clean(self):
        if self.month and self.month.day != 1:
            raise ValidationError("month oyning birinchi kuni bo'lishi kerak.")

        if self.group_id and self.student_id:
            is_group_student = self.group.groupstudent_set.filter(
                student_id=self.student_id,
                is_active=True,
                student__is_active=True,
            ).exists()
            if not is_group_student:
                raise ValidationError("Bu o'quvchi ushbu guruhga biriktirilmagan.")

    def save(self, *args, **kwargs):
        self.refresh_status()
        super().save(*args, **kwargs)


class PaymentTransaction(models.Model):
    student = models.ForeignKey(
        'students.Student',
        on_delete=models.PROTECT,
        related_name='payments',
    )
    group = models.ForeignKey(
        'groups_app.Group',
        on_delete=models.PROTECT,
        related_name='payments',
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    payment_date = models.DateField()
    method = models.CharField(max_length=20, choices=PaymentMethod.choices, default=PaymentMethod.CASH)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='created_payments',
        null=True,
        blank=True,
    )
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-payment_date', '-created_at')
        verbose_name = "To'lov"
        verbose_name_plural = "To'lovlar"

    def __str__(self):
        return f'{self.student} - {self.amount}'


class PaymentAllocation(models.Model):
    payment = models.ForeignKey(
        PaymentTransaction,
        on_delete=models.CASCADE,
        related_name='allocations',
    )
    balance = models.ForeignKey(
        StudentMonthBalance,
        on_delete=models.PROTECT,
        related_name='payment_allocations',
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )

    class Meta:
        ordering = ('balance__month',)
        verbose_name = "To'lov taqsimoti"
        verbose_name_plural = "To'lov taqsimotlari"

    def __str__(self):
        return f'{self.balance} - {self.amount}'
