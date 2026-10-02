from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Exists, F, OuterRef
from django.utils import timezone


class MonthBalanceStatus(models.TextChoices):
    OPEN = 'OPEN', 'Ochiq'
    PARTIAL = 'PARTIAL', 'Qisman'
    CLOSED = 'CLOSED', 'Yopildi'


class PaymentMethod(models.TextChoices):
    CASH = 'CASH', 'Naqd'
    CARD = 'CARD', 'Karta'
    TRANSFER = 'TRANSFER', "O'tkazma"


class StudentMonthBalanceQuerySet(models.QuerySet):
    def due(self, as_of=None):
        """To'lov muddati kelgan oylar (kelgusi oylar uchun avanslar kirmaydi)."""
        return self.filter(due_date__lte=as_of or timezone.localdate())

    def not_due(self, as_of=None):
        return self.filter(due_date__gt=as_of or timezone.localdate())

    def with_debt(self):
        return self.filter(paid_amount__lt=F('required_amount'))

    def debts(self, as_of=None):
        """Haqiqiy qarzlar: muddati kelgan va to'liq to'lanmagan oylar."""
        return self.due(as_of).with_debt()

    def current_members(self):
        """Hozir ham guruhda o'qiyotgan faol o'quvchilarning balanslari."""
        from groups_app.models import GroupStudent
        membership = GroupStudent.objects.filter(
            student=OuterRef('student'), group=OuterRef('group'), is_active=True,
        )
        return self.filter(Exists(membership), student__is_active=True, group__is_active=True)

    def former_members(self):
        """Ketgan / o'chirilgan / guruhdan chiqqan o'quvchilar yoki yopilgan guruhlar."""
        return self.exclude(pk__in=self.current_members().values('pk'))


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
    # Shu oy davrining boshlanish sanasi (guruh boshlangan kun bo'yicha). Qarz faqat shu sanadan keyin hisoblanadi.
    due_date = models.DateField(null=True, blank=True, db_index=True)
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

    objects = StudentMonthBalanceQuerySet.as_manager()

    class Meta:
        unique_together = ('student', 'group', 'month')
        ordering = ('student__last_name', 'student__first_name', 'month')
        verbose_name = "Oylik balans"
        verbose_name_plural = "Oylik balanslar"

    def __str__(self):
        return f'{self.student} - {self.group} - {self.month:%Y-%m}'

    @property
    def is_due(self):
        return self.due_date is None or self.due_date <= timezone.localdate()

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
        # Oyning birinchi kuni bo'lishi kerakligi haqidagi qat'iy talab olib tashlandi
        # lekin ma'lumotlar bazasida 1-kun sifatida saqlanishi tavsiya etiladi.
        if self.month:
            self.month = self.month.replace(day=1)

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
        validators=[MinValueValidator(Decimal('0'))],
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
    # Bir xil so'rov takrorlansa (qayta urinish, ikki marta bosish) ikkinchi to'lov yaratilmasligi uchun.
    idempotency_key = models.UUIDField(null=True, blank=True, unique=True, editable=False)
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
        validators=[MinValueValidator(Decimal('0'))],
    )

    class Meta:
        ordering = ('balance__month',)
        verbose_name = "To'lov taqsimoti"
        verbose_name_plural = "To'lov taqsimotlari"

    def __str__(self):
        return f'{self.balance} - {self.amount}'


class BillingPause(models.Model):
    """To'lov hisoblanmaydigan davr.

    * faqat student — o'quvchi muzlatilgan (barcha guruhlari bo'yicha);
    * faqat group — guruh vaqtincha to'xtatilgan;
    * ikkalasi — o'quvchi guruhdan chiqib, keyin qaytgan oraliq.

    Muddati (due_date) start_date..end_date oralig'iga tushgan oylar hisoblanmaydi;
    end_date tushgan oy (qaytgan oy) hisoblanadi.
    """
    student = models.ForeignKey('students.Student', on_delete=models.CASCADE, null=True, blank=True,
                                related_name='billing_pauses')
    group = models.ForeignKey('groups_app.Group', on_delete=models.CASCADE, null=True, blank=True,
                              related_name='billing_pauses')
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    reason = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-start_date',)
        verbose_name = "To'lov pauzasi"
        verbose_name_plural = "To'lov pauzalari"

    def clean(self):
        if not self.student_id and not self.group_id:
            raise ValidationError("O'quvchi yoki guruh ko'rsatilishi kerak.")
        if self.end_date and self.end_date < self.start_date:
            raise ValidationError("Tugash sanasi boshlanish sanasidan oldin bo'lishi mumkin emas.")

    def __str__(self):
        who = ' / '.join(str(x) for x in (self.student, self.group) if x)
        return f'{who}: {self.start_date} — {self.end_date or "..."}'
