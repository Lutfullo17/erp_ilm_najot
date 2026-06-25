from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models


class Group(models.Model):
    name = models.CharField(max_length=150, unique=True)
    monthly_fee = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=500000,
        validators=[MinValueValidator(1)],
    )
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='teaching_groups',
        limit_choices_to={'role': 'TEACHER'},
    )
    students = models.ManyToManyField(
        'students.Student',
        through='GroupStudent',
        related_name='groups',
        blank=True,
    )
    start_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('name',)
        verbose_name = 'Guruh'
        verbose_name_plural = 'Guruhlar'

    def __str__(self):
        return self.name

    def clean(self):
        if self.teacher_id and not self.teacher.is_teacher:
            raise ValidationError("Guruh o'qituvchisi TEACHER role'da bo'lishi kerak.")


class GroupStudent(models.Model):
    group = models.ForeignKey(Group, on_delete=models.CASCADE)
    student = models.ForeignKey('students.Student', on_delete=models.CASCADE)
    joined_at = models.DateField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ('group', 'student')
        verbose_name = "Guruh o'quvchisi"
        verbose_name_plural = "Guruh o'quvchilari"

    def __str__(self):
        return f'{self.student} - {self.group}'
