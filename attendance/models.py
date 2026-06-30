from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class AttendanceStatus(models.TextChoices):
    PRESENT = 'PRESENT', 'Keldi'
    ABSENT = 'ABSENT', 'Kelmadi'
    EXCUSED = 'EXCUSED', 'Sababli'
    LATE = 'LATE', 'Kechikdi'


class AttendanceSession(models.Model):
    group = models.ForeignKey(
        'groups_app.Group',
        on_delete=models.PROTECT,
        related_name='attendance_sessions',
    )
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='attendance_sessions',
        limit_choices_to={'role': 'TEACHER'},
    )
    date = models.DateField()
    lesson_topic = models.CharField(max_length=255, blank=True, verbose_name="Dars mavzusi")
    homework = models.TextField(blank=True, verbose_name="Uyga vazifa")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('group', 'date')
        ordering = ('-date', 'group__name')
        verbose_name = 'Davomat'
        verbose_name_plural = 'Davomatlar'

    def __str__(self):
        return f'{self.group} - {self.date}'

    def clean(self):
        if self.group_id and self.teacher_id and self.group.teacher_id != self.teacher_id:
            raise ValidationError("Davomatni faqat guruh o'qituvchisi yurita oladi.")


class AttendanceRecord(models.Model):
    session = models.ForeignKey(
        AttendanceSession,
        on_delete=models.CASCADE,
        related_name='records',
    )
    student = models.ForeignKey(
        'students.Student',
        on_delete=models.PROTECT,
        related_name='attendance_records',
    )
    status = models.CharField(max_length=20, choices=AttendanceStatus.choices)
    comment = models.CharField(max_length=255, blank=True)
    marked_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('session', 'student')
        ordering = ('student__last_name', 'student__first_name')
        verbose_name = 'Davomat yozuvi'
        verbose_name_plural = 'Davomat yozuvlari'

    def __str__(self):
        return f'{self.student} - {self.get_status_display()}'

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


class LessonPlan(models.Model):
    group = models.ForeignKey(
        'groups_app.Group',
        on_delete=models.CASCADE,
        related_name='lesson_plans',
    )
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='lesson_plans',
    )
    date = models.DateField(verbose_name="Sana")
    topic = models.CharField(max_length=255, verbose_name="Mavzu")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('group', 'date')
        ordering = ('date',)
        verbose_name = 'Dars rejalashtirish'
        verbose_name_plural = 'Dars rejalari'

    def __str__(self):
        return f'{self.group} - {self.date}: {self.topic}'
