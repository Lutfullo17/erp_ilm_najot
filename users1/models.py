from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        DIRECTOR = 'DIRECTOR', 'Director'
        ADMINISTRATOR = 'ADMINISTRATOR', 'Administrator'
        TEACHER = 'TEACHER', "O'qituvchi"

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.TEACHER,
    )
    phone = models.CharField(max_length=20, blank=True, verbose_name="Telefon")
    photo = models.ImageField(upload_to='avatars/', blank=True, null=True, verbose_name="Profil rasmi")
    is_blocked = models.BooleanField(default=False, verbose_name="Bloklangan")
    is_deleted = models.BooleanField(default=False, verbose_name="O'chirilgan")
    deleted_at = models.DateTimeField(null=True, blank=True, verbose_name="O'chirilgan vaqt")
    deleted_by = models.ForeignKey(
        'users1.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='deleted_users',
        verbose_name="Kim o'chirdi"
    )

    @property
    def is_director(self):
        return self.role == self.Role.DIRECTOR or self.is_superuser

    @property
    def is_administrator_role(self):
        return self.role == self.Role.ADMINISTRATOR

    @property
    def is_admin_access(self):
        """Returns True if the user has Director or Administrator access"""
        return self.role in [self.Role.DIRECTOR, self.Role.ADMINISTRATOR] or self.is_superuser

    @property
    def is_teacher(self):
        return self.role == self.Role.TEACHER

    def save(self, *args, **kwargs):
        if self.is_superuser:
            self.role = self.Role.DIRECTOR
        super().save(*args, **kwargs)


class TeacherManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(role=User.Role.TEACHER)


class Teacher(User):
    objects = TeacherManager()

    class Meta:
        proxy = True
        verbose_name = "O'qituvchi"
        verbose_name_plural = "O'qituvchilar"

    def save(self, *args, **kwargs):
        self.role = User.Role.TEACHER
        super().save(*args, **kwargs)


class AuditLog(models.Model):
    """Barcha muhim amallarni qayd qilish uchun (yagona AuditLog)"""
    user = models.ForeignKey(
        'users1.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='audit_logs_created',
        verbose_name="Kim bajardi"
    )
    target_user = models.ForeignKey(
        'users1.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs_target',
        verbose_name="Kim haqida"
    )
    role = models.CharField(max_length=50, blank=True, default='', verbose_name="Rol")
    action = models.CharField(max_length=255, verbose_name="Amal")
    old_data = models.JSONField(null=True, blank=True, verbose_name="Eski ma'lumot")
    new_data = models.JSONField(null=True, blank=True, verbose_name="Yangi ma'lumot")
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name="IP manzil")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Sana va vaqt")

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Audit Log"
        verbose_name_plural = "Audit Loglar"

    def __str__(self):
        return f"{self.user} → {self.action} [{self.created_at.strftime('%d.%m.%Y %H:%M')}]"


class TeacherPenalty(models.Model):
    """Teacher jarima ballari tizimi"""
    class PenaltyType(models.TextChoices):
        ATTENDANCE_MISSED = 'ATTENDANCE_MISSED', "Davomat olinmadi (darsga keldi)"
        CLASS_SKIPPED = 'CLASS_SKIPPED', "Darsga kelmadi"
        CONSECUTIVE_MISSED = 'CONSECUTIVE_MISSED', "Ketma-ket davomat olinmadi"
        MANUAL = 'MANUAL', "Qo'lda kiritildi"

    teacher = models.ForeignKey(
        'users1.User',
        on_delete=models.CASCADE,
        related_name='penalties',
        limit_choices_to={'role': 'TEACHER'},
        verbose_name="O'qituvchi"
    )
    group = models.ForeignKey(
        'groups_app.Group',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Guruh"
    )
    date = models.DateField(verbose_name="Dars sanasi")
    reason = models.CharField(max_length=255, verbose_name="Jarima sababi")
    points = models.IntegerField(default=0, verbose_name="Minus ball")
    penalty_type = models.CharField(
        max_length=30,
        choices=PenaltyType.choices,
        default=PenaltyType.ATTENDANCE_MISSED,
        verbose_name="Jarima turi"
    )
    is_manual = models.BooleanField(default=False, verbose_name="Qo'lda berildi")
    given_by = models.ForeignKey(
        'users1.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='penalties_given',
        verbose_name="Kim berdi"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Yaratilgan vaqt")

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Jarima"
        verbose_name_plural = "Jarimalar"

    def __str__(self):
        return f"{self.teacher.get_full_name()} - {self.points} ball - {self.date}"


class MissedAttendanceAlert(models.Model):
    """Davomat olinmagan holatlar uchun ogohlantirish"""
    class Status(models.TextChoices):
        PENDING = 'PENDING', "Kutilmoqda"
        CAME = 'CAME', "Keldi (davomat olinsin)"
        NOT_CAME = 'NOT_CAME', "Kelmadi (-10 ball)"
        RESOLVED = 'RESOLVED', "Hal qilindi"

    teacher = models.ForeignKey(
        'users1.User',
        on_delete=models.CASCADE,
        related_name='missed_alerts',
        verbose_name="O'qituvchi"
    )
    group = models.ForeignKey(
        'groups_app.Group',
        on_delete=models.CASCADE,
        verbose_name="Guruh"
    )
    lesson_date = models.DateField(verbose_name="Dars sanasi")
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name="Holati"
    )
    penalty_applied = models.BooleanField(default=False, verbose_name="Jarima berildi")
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        'users1.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resolved_alerts',
        verbose_name="Kim hal qildi"
    )

    class Meta:
        unique_together = ('teacher', 'group', 'lesson_date')
        ordering = ['-created_at']
        verbose_name = "Davomat ogohlantirishi"
        verbose_name_plural = "Davomat ogohlantirishlari"

    def __str__(self):
        return f"{self.teacher} - {self.group} - {self.lesson_date}"


class ScheduleChangeRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Kutilmoqda'
        APPROVED = 'APPROVED', 'Tasdiqlandi'
        REJECTED = 'REJECTED', 'Rad etildi'
        CANCELLED = 'CANCELLED', 'Bekor qilindi'

    class ChangeType(models.TextChoices):
        ADMIN_DIRECT = 'ADMIN_DIRECT', "Admin to'g'ridan-to'g'ri"
        TEACHER_REQUEST = 'TEACHER_REQUEST', "O'qituvchi arizasi"

    teacher = models.ForeignKey(
        'users1.User',
        on_delete=models.CASCADE,
        related_name='schedule_change_requests',
        limit_choices_to={'role': 'TEACHER'},
        verbose_name="O'qituvchi"
    )
    group = models.ForeignKey(
        'groups_app.Group',
        on_delete=models.CASCADE,
        verbose_name="Guruh"
    )
    old_day = models.CharField(max_length=20, verbose_name="Hozirgi dars kuni")
    old_start_time = models.TimeField(verbose_name="Hozirgi boshlanish vaqti")
    old_end_time = models.TimeField(verbose_name="Hozirgi tugash vaqti")
    new_day = models.CharField(max_length=20, verbose_name="Yangi dars kuni")
    new_start_time = models.TimeField(verbose_name="Yangi boshlanish vaqti")
    new_end_time = models.TimeField(verbose_name="Yangi tugash vaqti")
    reason = models.TextField(verbose_name="Sabab")
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name="Holati"
    )
    submitted_at = models.DateTimeField(auto_now_add=True, verbose_name="Yuborilgan sana")
    effective_week_start = models.DateField(null=True, blank=True, verbose_name="Qaysi hafta uchun amal qiladi")
    reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name="Ko'rib chiqilgan sana")
    reviewed_by = models.ForeignKey(
        'users1.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='schedule_requests_reviewed',
        verbose_name="Kim ko'rib chiqdi"
    )
    review_comment = models.TextField(blank=True, default='', verbose_name="Ko'rib chiqish izohi")
    change_date = models.DateField(null=True, blank=True, verbose_name="Qaysi sana uchun o'zgarish")
    change_type = models.CharField(
        max_length=20,
        choices=ChangeType.choices,
        default=ChangeType.TEACHER_REQUEST,
        verbose_name="O'zgartirish turi"
    )

    class Meta:
        ordering = ['-submitted_at']
        verbose_name = "Jadval o'zgartirish arizasi"
        verbose_name_plural = "Jadval o'zgartirish arizalari"

    def __str__(self):
        return f"{self.teacher.get_full_name()} - {self.group.name} - {self.status}"
