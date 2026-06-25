from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import PaymentTransaction
from bot.notifications import notify_payment_received

@receiver(post_save, sender=PaymentTransaction)
def payment_saved(sender, instance, created, **kwargs):
    if created:
        notify_payment_received(instance)
