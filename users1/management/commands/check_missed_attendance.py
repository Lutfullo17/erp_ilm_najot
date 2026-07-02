"""
Management command: check_missed_attendance

Dars vaqti tugagan, lekin davomat olinmagan guruhlar uchun
MissedAttendanceAlert yaratadi. Alertlar faqat dashboard orqali ko'rinadi.

Ishlatilishi:
    python manage.py check_missed_attendance

Scheduler (APScheduler yoki cron) orqali har 15 daqiqada chaqirish tavsiya etiladi.
"""
from django.core.management.base import BaseCommand

from users1.penalty_service import check_and_create_missed_alerts


class Command(BaseCommand):
    help = 'Davomat olinmagan guruhlar uchun ogohlantirishlar yaratadi'

    def handle(self, *args, **options):
        created_count = check_and_create_missed_alerts()

        self.stdout.write(
            self.style.SUCCESS(
                f"{created_count} ta yangi ogohlantirish yaratildi."
            )
        )
