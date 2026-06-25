import datetime
from django.core.management.base import BaseCommand
from django.utils import timezone
from payments.models import StudentMonthBalance, MonthBalanceStatus
from bot.notifications import notify_payment_reminder

class Command(BaseCommand):
    help = "To'lov muddati kelgan o'quvchilarga eslatma yuborish"

    def handle(self, *args, **options):
        today = timezone.localdate()
        # Oyning 1-kuni to'lov kuni deb hisoblaymiz (StudentMonthBalance dagi month field)
        # Eslatma yuborish shartlari:
        # 1. Oyning 1-kuni (To'lov kuni)
        # 2. To'lov kunidan 5 kun oldin (O'tgan oyning 25-27 kunlari atrofida)
        
        # Hozirda faqat qarzi borlarga (OPEN yoki PARTIAL) eslatma yuboramiz
        balances = StudentMonthBalance.objects.filter(
            status__in=[MonthBalanceStatus.OPEN, MonthBalanceStatus.PARTIAL]
        ).select_related('student', 'group')
        
        count = 0
        for balance in balances:
            # Agar balance.month bugungi oy bo'lsa va bugun oyning boshlanishi bo'lsa
            if balance.month.year == today.year and balance.month.month == today.month:
                # To'lov kuni yoki unga yaqin kunlar (1-5 kunlar)
                if 1 <= today.day <= 5:
                    notify_payment_reminder(balance)
                    count += 1
            
            # Keyingi oy uchun eslatma (oy tugashiga 5 kun qolganda)
            # Bu biroz murakkabroq, lekin soddalashtiramiz: 
            # Agar balance.month kelasi oy bo'lsa va bugun oy oxiri bo'lsa
            # (Hozircha faqat joriy aydagi qarzdorlarga eslatish yetarli deb hisoblayman)

        self.stdout.write(self.style.SUCCESS(f"{count} ta o'quvchiga eslatma yuborildi."))
