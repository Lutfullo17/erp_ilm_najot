"""
Management command: check_missed_attendance

Dars vaqti tugagan, lekin davomat olinmagan guruhlar uchun
MissedAttendanceAlert yaratadi va Admin/Director'ga Telegram xabar yuboradi.

Ishlatilishi:
    python manage.py check_missed_attendance

Scheduler (APScheduler yoki cron) orqali har 15 daqiqada chaqirish tavsiya etiladi.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from groups_app.models import Group
from attendance.models import AttendanceSession
from users1.models import MissedAttendanceAlert, User


class Command(BaseCommand):
    help = 'Davomat olinmagan guruhlar uchun ogohlantirishlar yaratadi'

    def handle(self, *args, **options):
        today = timezone.localdate()
        now_time = timezone.localtime().time()

        days_map = {
            0: 'Dushanba', 1: 'Seshanba', 2: 'Chorshanba', 3: 'Payshanba',
            4: 'Juma', 5: 'Shanba', 6: 'Yakshanba'
        }
        today_name = days_map[today.weekday()]

        # Bugun dars bo'lgan, vaqti o'tgan, lekin davomat olinmagan guruhlar
        groups = Group.objects.filter(
            is_active=True,
            lesson_days__contains=today_name,
            end_time__lt=now_time,
            teacher__isnull=False,
        ).select_related('teacher')

        created_count = 0
        notified_count = 0

        for group in groups:
            has_session = AttendanceSession.objects.filter(
                group=group,
                date=today,
            ).exists()

            if not has_session:
                alert, created = MissedAttendanceAlert.objects.get_or_create(
                    teacher=group.teacher,
                    group=group,
                    lesson_date=today,
                    defaults={'status': MissedAttendanceAlert.Status.PENDING}
                )
                if created:
                    created_count += 1
                    # Telegram xabar yuborish
                    try:
                        sent = _notify_missed_attendance(alert)
                        if sent:
                            notified_count += 1
                    except Exception as e:
                        self.stderr.write(f"Xabar yuborishda xatolik: {e}")

        self.stdout.write(
            self.style.SUCCESS(
                f"✅ {created_count} ta yangi ogohlantirish yaratildi, "
                f"{notified_count} ta xabar yuborildi."
            )
        )


def _notify_missed_attendance(alert):
    """Director va Administrator'larga Telegram xabar yuboradi."""
    try:
        from bot.services import send_telegram_message
        from bot.models import TelegramUser
    except ImportError:
        return False

    teacher = alert.teacher
    group = alert.group
    lesson_date = alert.lesson_date

    teacher_name = teacher.get_full_name() or teacher.username
    time_str = ''
    if group.lesson_time:
        time_str = f"{group.lesson_time.strftime('%H:%M')}"
    if group.end_time:
        time_str += f" - {group.end_time.strftime('%H:%M')}"

    message = (
        f"⚠️ <b>Davomat olinmadi!</b>\n\n"
        f"📚 Guruh: <b>{group.name}</b>\n"
        f"👨‍🏫 O'qituvchi: <b>{teacher_name}</b>\n"
        f"🕐 Vaqt: {time_str}\n"
        f"📅 Sana: {lesson_date.strftime('%d.%m.%Y')}\n\n"
        f"❓ O'qituvchi darsga keldimi?\n"
        f"Iltimos, tizimda tekshiring va holat belgilang."
    )

    # Director va Administratorlarning Telegram ID larini topish
    # (ular Students bilan bog'liq emas, shuning uchun boshqacha yo'l kerak)
    # Bu yerda settings'da DIRECTOR_TELEGRAM_ID yoki alohida model kerak bo'ladi
    # Hozircha biz faqat existing TelegramUser'larni ishlatamiz
    # Keyingi versiyada Director/Admin uchun alohida Telegram profil qo'shish kerak

    sent = False

    # Agar Director/Admin'larni TelegramUser orqali topa olsak
    directors_admins = User.objects.filter(
        role__in=[User.Role.DIRECTOR, User.Role.ADMINISTRATOR],
        is_blocked=False,
    )
    for staff in directors_admins:
        # TelegramUser bilan bog'lanish (student orqali emas, username orqali)
        # Bu kelajakda implement qilinadi
        pass

    return sent
