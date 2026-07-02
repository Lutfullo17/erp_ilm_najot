from django.db import models


class Student(models.Model):
    class Gender(models.TextChoices):
        MALE = 'MALE', 'Erkak'
        FEMALE = 'FEMALE', 'Ayol'

    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Faol'
        FROZEN = 'FROZEN', 'Muzlatilgan'
        LEFT = 'LEFT', 'Ketgan'

    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20, blank=True)
    secondary_phone = models.CharField(max_length=20, blank=True, verbose_name="Qo'shimcha telefon")
    parent_phone = models.CharField(max_length=20, blank=True, verbose_name="Ota-ona telefon raqami")
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

    class Meta:
        ordering = ('last_name', 'first_name')
        verbose_name = "O'quvchi"
        verbose_name_plural = "O'quvchilar"

    def __str__(self):
        return f'{self.first_name} {self.last_name}'
