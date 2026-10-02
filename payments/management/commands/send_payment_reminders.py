import datetime
from django.core.management.base import BaseCommand
from django.utils import timezone
from payments.models import StudentMonthBalance
from bot.notifications import notify_payment_reminder

# To'lov muddati kelganidan keyin necha kun davomida eslatma yuboriladi
REMINDER_DAYS = 5


class Command(BaseCommand):
    help = "To'lov muddati kelgan o'quvchilarga eslatma yuborish"

    def handle(self, *args, **options):
        today = timezone.localdate()
        # Faqat hozir o'qiyotgan o'quvchilarning, muddati oxirgi REMINDER_DAYS kun ichida kelgan qarzlari
        balances = StudentMonthBalance.objects.debts(today).current_members().filter(
            due_date__gt=today - datetime.timedelta(days=REMINDER_DAYS),
        ).select_related('student', 'group')

        count = 0
        for balance in balances:
            notify_payment_reminder(balance)
            count += 1

        self.stdout.write(self.style.SUCCESS(f"{count} ta o'quvchiga eslatma yuborildi."))
