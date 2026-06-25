from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import AttendanceRecord
from bot.notifications import notify_attendance_absent

@receiver(post_save, sender=AttendanceRecord)
def attendance_saved(sender, instance, created, **kwargs):
    if instance.status == 'ABSENT':
        # We notify even if updated to ABSENT, or if created as ABSENT
        notify_attendance_absent(instance)
