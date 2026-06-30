from django.db import models


class TelegramUser(models.Model):
    telegram_id = models.BigIntegerField(unique=True)
    username = models.CharField(max_length=150, blank=True)
    first_name = models.CharField(max_length=150, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    student = models.ForeignKey(
        'students.Student',
        on_delete=models.PROTECT,
        related_name='telegram_users',
        null=True,
        blank=True,
    )
    user = models.ForeignKey(
        'users1.User',
        on_delete=models.SET_NULL,
        related_name='telegram_users',
        null=True,
        blank=True,
        verbose_name="Admin/O'qituvchi",
    )
    is_verified = models.BooleanField(default=False)
    state = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-updated_at',)
        verbose_name = 'Telegram foydalanuvchi'
        verbose_name_plural = 'Telegram foydalanuvchilar'

    def __str__(self):
        return self.username or self.first_name or str(self.telegram_id)


class TelegramAppeal(models.Model):
    class SenderType(models.TextChoices):
        STUDENT = 'STUDENT', 'O\'quvchi'
        ADMIN = 'ADMIN', 'Admin'
        TEACHER = 'TEACHER', 'O\'qituvchi'

    telegram_user = models.ForeignKey(
        TelegramUser,
        on_delete=models.CASCADE,
        related_name='appeals',
    )
    student = models.ForeignKey(
        'students.Student',
        on_delete=models.PROTECT,
        related_name='telegram_appeals',
    )
    message = models.TextField()
    sender_type = models.CharField(
        max_length=20,
        choices=SenderType.choices,
        default=SenderType.STUDENT,
        verbose_name="Xabar turi",
    )
    recipient_type = models.CharField(
        max_length=20,
        choices=SenderType.choices,
        blank=True,
        verbose_name="Kimga yuborildi",
    )
    is_resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at',)
        verbose_name = 'Murojaat'
        verbose_name_plural = 'Murojaatlar'

    def __str__(self):
        return f'{self.student} - {self.created_at:%Y-%m-%d}'


class TeacherMessage(models.Model):
    class Status(models.TextChoices):
        SENT = 'SENT', 'Yuborildi'
        FAILED = 'FAILED', 'Xatolik'

    teacher = models.ForeignKey(
        'users1.User',
        on_delete=models.PROTECT,
        related_name='teacher_messages',
    )
    student = models.ForeignKey(
        'students.Student',
        on_delete=models.PROTECT,
        related_name='teacher_messages',
    )
    parent = models.ForeignKey(
        TelegramUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='received_teacher_messages',
    )
    message = models.TextField()
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.SENT,
    )
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-sent_at',)
        verbose_name = "O'qituvchi xabari"
        verbose_name_plural = "O'qituvchi xabarlar"

    def __str__(self):
        return f'{self.teacher} -> {self.student}: {self.message[:50]}'
