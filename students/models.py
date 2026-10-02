from decimal import Decimal

from django.db import models


class Parent(models.Model):
    """Ota-ona modeli — bir ota-ona bir nechta farzandga ega bo'lishi mumkin."""
    phone = models.CharField(max_length=20, unique=True, verbose_name="Telefon raqami")
    first_name = models.CharField(max_length=150, blank=True, verbose_name="Ism")
    last_name = models.CharField(max_length=150, blank=True, verbose_name="Familiya")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('last_name', 'first_name')
        verbose_name = "Ota-ona"
        verbose_name_plural = "Ota-onalar"

    def __str__(self):
        full_name = f'{self.first_name} {self.last_name}'.strip()
        return full_name if full_name else self.phone

    @property
    def children(self):
        """Ota-onaning barcha farzandlari."""
        return Student.objects.filter(parent=self, is_active=True)


class Student(models.Model):
    class Gender(models.TextChoices):
        MALE = 'MALE', 'Erkak'
        FEMALE = 'FEMALE', 'Ayol'

    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Faol'
        FROZEN = 'FROZEN', 'Muzlatilgan'
        LEFT = 'LEFT', 'Ketgan'

    class DiscountType(models.TextChoices):
        PERCENTAGE = 'PERCENTAGE', 'Foiz (%)'
        FIXED = 'FIXED', "Summa (so'm)"

    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20, blank=True)
    secondary_phone = models.CharField(max_length=20, blank=True, verbose_name="Qo'shimcha telefon")
    parent_phone = models.CharField(max_length=20, blank=True, verbose_name="Ota-ona telefon raqami")
    parent = models.ForeignKey(
        Parent,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='children_set',
        verbose_name="Ota-ona"
    )
    birth_date = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=10, choices=Gender.choices, default=Gender.MALE, verbose_name="Jinsi")
    address = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE, verbose_name="Holati")
    is_active = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False, verbose_name="O'chirilgan")
    deleted_at = models.DateTimeField(null=True, blank=True, verbose_name="O'chirilgan vaqt")
    deleted_by = models.ForeignKey(
        'users1.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='deleted_students',
        verbose_name="Kim o'chirdi"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    # Chegirma tizimi
    has_discount = models.BooleanField(default=False, verbose_name="Chegirmasi bormi")
    discount_type = models.CharField(
        max_length=20,
        choices=DiscountType.choices,
        default=DiscountType.PERCENTAGE,
        blank=True,
        verbose_name="Chegirma turi"
    )
    discount_value = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name="Chegirma qiymati"
    )

    class Meta:
        ordering = ('last_name', 'first_name')
        verbose_name = "O'quvchi"
        verbose_name_plural = "O'quvchilar"

    def __str__(self):
        return f'{self.first_name} {self.last_name}'

    def get_full_name(self):
        if self.last_name:
            return f"{self.first_name} {self.last_name[0]}."
        return self.first_name

    def get_effective_fee(self, group_monthly_fee):
        """Chegirma hisobga olingan oylik to'lovni hisoblaydi."""
        if not self.has_discount or not self.discount_value:
            return Decimal(str(group_monthly_fee))

        fee = Decimal(str(group_monthly_fee))
        if self.discount_type == self.DiscountType.PERCENTAGE:
            discount = fee * Decimal(str(self.discount_value)) / Decimal('100')
            return max(fee - discount, Decimal('0'))
        elif self.discount_type == self.DiscountType.FIXED:
            return max(fee - Decimal(str(self.discount_value)), Decimal('0'))
        return fee

    @property
    def has_debt(self):
        """O'quvchining kamida bitta ochiq qarzi bor-yo'qligini tekshiradi."""
        from payments.models import StudentMonthBalance
        return StudentMonthBalance.objects.debts().filter(student=self).exists()

    @property
    def discount_display(self):
        """Chegirmani ko'rsatish uchun matn."""
        if not self.has_discount or not self.discount_value:
            return ""
        if self.discount_type == self.DiscountType.PERCENTAGE:
            return f"{self.discount_value}%"
        return f"{self.discount_value:,.0f} so'm".replace(',', ' ')
