from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import GradeRecord
from bot.notifications import notify_grade_added

@receiver(post_save, sender=GradeRecord)
def grade_saved(sender, instance, created, **kwargs):
    if created:
        notify_grade_added(instance)
