from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class GradeSession(models.Model):
    group = models.ForeignKey(
        'groups_app.Group',
        on_delete=models.PROTECT,
        related_name='grade_sessions',
    )
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='grade_sessions',
        limit_choices_to={'role': 'TEACHER'},
    )
    title = models.CharField(max_length=150, default='Dars bahosi')
    date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('group', 'date', 'title')
        ordering = ('-date', 'group__name', 'title')
        verbose_name = 'Baho'
        verbose_name_plural = 'Baholar'

    def __str__(self):
        return f'{self.group} - {self.title} - {self.date}'

    def clean(self):
        if self.group_id and self.teacher_id and self.group.teacher_id != self.teacher_id:
            raise ValidationError("Bahoni faqat guruh o'qituvchisi qo'ya oladi.")


class GradeRecord(models.Model):
    session = models.ForeignKey(
        GradeSession,
        on_delete=models.CASCADE,
        related_name='records',
    )
    student = models.ForeignKey(
        'students.Student',
        on_delete=models.PROTECT,
        related_name='grade_records',
    )
    percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[
            MinValueValidator(Decimal('0')),
            MaxValueValidator(Decimal('100')),
        ],
    )
    comment = models.CharField(max_length=255, blank=True)
    graded_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('session', 'student')
        ordering = ('student__last_name', 'student__first_name')
        verbose_name = 'Baho yozuvi'
        verbose_name_plural = 'Baho yozuvlari'

    def __str__(self):
        return f'{self.student} - {self.percentage}%'

    def clean(self):
        if not self.session_id or not self.student_id:
            return

        is_group_student = self.session.group.groupstudent_set.filter(
            student_id=self.student_id,
            is_active=True,
            student__is_active=True,
        ).exists()

        if not is_group_student:
            raise ValidationError("Bu o'quvchi ushbu guruhga biriktirilmagan.")
