from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import AttendanceRecord

@receiver(post_save, sender=AttendanceRecord)
def attendance_saved(sender, instance, created, **kwargs):
    if instance.status == 'ABSENT':
        try:
            from bot.notifications import notify_attendance_absent
            notify_attendance_absent(instance)
        except Exception:
            pass
