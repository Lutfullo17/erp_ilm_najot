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
    is_resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at',)
        verbose_name = 'Murojaat'
        verbose_name_plural = 'Murojaatlar'

    def __str__(self):
        return f'{self.student} - {self.created_at:%Y-%m-%d}'
