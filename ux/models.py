from django.conf import settings
from django.db import models


class Feedback(models.Model):
    """Yangi interfeysdagi "Fikr bildirish" tugmasidan kelgan xabarlar."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='ux_feedback')
    page = models.CharField(max_length=255, blank=True)
    message = models.TextField(max_length=1000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Fikr'
        verbose_name_plural = 'Fikrlar'

    def __str__(self):
        return f'{self.user} — {self.message[:40]}'
