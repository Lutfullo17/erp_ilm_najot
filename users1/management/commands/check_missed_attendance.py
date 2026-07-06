"""
Management command: check_missed_attendance

Dars vaqti tugagan, lekin davomat olinmagan guruhlar uchun avtomatik nazorat tizimi.

Ishlatilishi:
    python manage.py check_missed_attendance

Har 5 daqiqada ishga tushirish tavsiya etiladi.
Cron example:
    */5 * * * * cd /path/to/project && python manage.py check_missed_attendance >> logs/attendance_monitor.log 2>&1
"""
import logging

from django.core.management.base import BaseCommand

from users1.penalty_service import check_and_create_missed_alerts

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Avtomatik davomat nazorat tizimini ishga tushiradi'

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.WARNING("Davomat nazorati boshlandi...")
        )

        try:
            result = check_and_create_missed_alerts()

            alerts_created = result.get('alerts_created', 0)
            reminders_sent = result.get('reminders_sent', 0)
            penalties_applied = result.get('penalties_applied', 0)

            self.stdout.write(
                self.style.SUCCESS(
                    f"Nazorat tugadi: "
                    f"{alerts_created} ta yangi ogohlantirish, "
                    f"{reminders_sent} ta eslatma yuborildi, "
                    f"{penalties_applied} ta jarima berildi."
                )
            )

            logger.info(
                f"Davomat nazorati: alerts={alerts_created}, "
                f"reminders={reminders_sent}, penalties={penalties_applied}"
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"Xatolik yuz berdi: {e}")
            )
            logger.error(f"Davomat nazoratida xatolik: {e}", exc_info=True)
