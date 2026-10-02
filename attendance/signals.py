import logging

from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import AttendanceRecord

logger = logging.getLogger(__name__)


@receiver(pre_save, sender=AttendanceRecord)
def attendance_pre_save(sender, instance, **kwargs):
    old = sender.objects.filter(pk=instance.pk).values_list('status', flat=True).first() if instance.pk else None
    instance._old_status = old


@receiver(post_save, sender=AttendanceRecord)
def attendance_saved(sender, instance, created, **kwargs):
    # Faqat "kelmadi" holatiga YANGI o'tilganda xabar yuboriladi (qayta saqlashda takrorlanmaydi).
    if instance.status != 'ABSENT' or getattr(instance, '_old_status', None) == 'ABSENT':
        return

    def _notify():
        try:
            from bot.notifications import notify_attendance_absent
            notify_attendance_absent(instance)
        except Exception:
            logger.exception('Davomat xabarini yuborishda xatolik')

    transaction.on_commit(_notify)
