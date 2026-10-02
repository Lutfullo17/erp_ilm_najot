from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from bot.notifications import notify_grade_added

from .models import GradeRecord


@receiver(post_save, sender=GradeRecord)
def grade_saved(sender, instance, created, **kwargs):
    if created:
        # Tranzaksiya rollback bo'lsa ota-onaga xabar ketmasligi uchun.
        transaction.on_commit(lambda: notify_grade_added(instance))
