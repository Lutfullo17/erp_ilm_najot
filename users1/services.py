from groups_app.models import Group

import datetime
import logging

logger = logging.getLogger(__name__)


def validate_teacher_deletion(teacher):
    """
    Teacher soft-delete qilinishidan oldin tekshirish.

    Guruh va dars yozuvlari o'qituvchi bilan FK orqali bog'langan bo'lsa ham,
    akkaunt fizik o'chirilmaydi. Faol guruhlar o'chirish view'ida yopiladi,
    shu sababli tarixiy va kelajak uchun kiritilgan davomat yozuvlarini saqlab
    qolish o'chirishga to'sqinlik qilmasligi kerak.
    """
    if teacher.is_deleted:
        return False, "Ushbu o'qituvchi allaqachon o'chirilgan."

    return True, None


def validate_student_deletion(student):
    """
    Student o'chirishdan oldin tekshirish:
    Faqat jiddiy bloklaydigan holatlarni tekshiradi.
    """
    if student.is_deleted:
        return False, "Ushbu o'quvchi allaqachon o'chirilgan."
    return True, None


def validate_schedule_change(group, new_day, new_start_time, new_end_time, new_room=None, new_teacher=None, exclude_pk=None):
    """
    Dars o'zgartirishini tekshirish:
    - Xona konflikti
    - O'qituvchi konflikti
    - Vaqt konflikti
    Xatoliklar ro'yxatini qaytaradi (bo'sh = xatolik yo'q).
    """
    errors = []

    check_room = new_room if new_room is not None else group.room
    check_teacher = new_teacher if new_teacher is not None else group.teacher

    # Xona konflikti
    if check_room:
        room_conflicts = Group.objects.filter(
            room=check_room,
            is_active=True,
            lesson_time__isnull=False,
        ).exclude(pk=group.pk)

        if exclude_pk:
            room_conflicts = room_conflicts.exclude(pk=exclude_pk)

        for other in room_conflicts:
            if not other.lesson_days:
                continue
            other_days = {d.strip() for d in other.lesson_days.split(',') if d.strip()}
            if new_day not in other_days:
                continue
            other_end = other.end_time
            if not other_end and other.lesson_time and other.duration:
                hours = int(other.duration)
                minutes = int((other.duration - hours) * 60)
                other_end = (datetime.datetime.combine(datetime.date.today(), other.lesson_time) + datetime.timedelta(hours=hours, minutes=minutes)).time()
            if other_end and new_start_time < other_end and new_end_time > other.lesson_time:
                errors.append(f"Xona band: {other.name} guruhi {new_day} kuni {other.lesson_time.strftime('%H:%M')}-{other_end.strftime('%H:%M')} vaqtida shu xonada.")

    # O'qituvchi konflikti
    if check_teacher:
        teacher_conflicts = Group.objects.filter(
            teacher=check_teacher,
            is_active=True,
            lesson_time__isnull=False,
        ).exclude(pk=group.pk)

        if exclude_pk:
            teacher_conflicts = teacher_conflicts.exclude(pk=exclude_pk)

        for other in teacher_conflicts:
            if not other.lesson_days:
                continue
            other_days = {d.strip() for d in other.lesson_days.split(',') if d.strip()}
            if new_day not in other_days:
                continue
            other_end = other.end_time
            if not other_end and other.lesson_time and other.duration:
                hours = int(other.duration)
                minutes = int((other.duration - hours) * 60)
                other_end = (datetime.datetime.combine(datetime.date.today(), other.lesson_time) + datetime.timedelta(hours=hours, minutes=minutes)).time()
            if other_end and new_start_time < other_end and new_end_time > other.lesson_time:
                errors.append(f"O'qituvchi band: {check_teacher.get_full_name()} {new_day} kuni {other.lesson_time.strftime('%H:%M')}-{other_end.strftime('%H:%M')} vaqtida {other.name} guruhibo'lda dars o'tmoqda.")

    return errors


def send_schedule_change_notifications(schedule_request):
    """
    Dars jadvali o'zgartirilganda xabarnoma yuborish:
    1. O'qituvchi dashboard (mavjud ScheduleChangeRequest orqali ko'rinadi)
    2. Telegram bot (ota-onalarga)
    """
    group = schedule_request.group

    try:
        from students.models import Student
        from bot.models import TelegramUser
        from bot.services import send_telegram_message

        students = Student.objects.filter(
            groupstudent__group=group,
            groupstudent__is_active=True,
            is_active=True,
        )

        old_time_str = schedule_request.old_start_time.strftime('%H:%M') if schedule_request.old_start_time else ''
        new_time_str = schedule_request.new_start_time.strftime('%H:%M') if schedule_request.new_start_time else ''
        change_date_str = schedule_request.change_date.strftime('%d.%m.%Y') if schedule_request.change_date else ''

        message = (
            f"<b>📅 Dars jadvali o'zgartirildi!</b>\n"
            f"──────────────────\n"
            f"📖 <b>Guruh:</b> {group.name}\n"
            f"📅 <b>Sana:</b> {change_date_str}\n"
            f"⏰ <b>Oldingi:</b> {schedule_request.old_day} {old_time_str}\n"
            f"⏰ <b>Yangi:</b> {schedule_request.new_day} {new_time_str}\n"
            f"📍 <b>Xona:</b> {group.get_room_display()}\n\n"
            f"O'zgartirish muvaffaqiyatli qo'llanildi."
        )

        parent_phones = students.values_list('parent_phone', flat=True).distinct()
        normalized_phones = []
        for p in parent_phones:
            if p:
                digits = ''.join(c for c in str(p) if c.isdigit())
                if len(digits) >= 9:
                    normalized_phones.append(digits[-9:])

        from django.db.models import Q
        q_phone = Q()
        for np in normalized_phones:
            q_phone |= Q(phone__endswith=np)

        telegram_users = TelegramUser.objects.filter(is_verified=True).filter(
            Q(student__in=students) | q_phone
        ).distinct()

        sent_count = 0
        for tu in telegram_users:
            try:
                result = send_telegram_message(tu.telegram_id, message)
                if result:
                    sent_count += 1
            except Exception as e:
                logger.error(f"Schedule change notification error: chat_id={tu.telegram_id}, error={e}")

        logger.info(f"Schedule change notifications sent: {sent_count}/{telegram_users.count()} for {group.name}")

    except Exception as e:
        logger.error(f"send_schedule_change_notifications error: {e}", exc_info=True)
