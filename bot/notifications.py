from django.conf import settings
from .services import send_telegram_message, money
from .models import TelegramUser


def notify_attendance_absent(attendance_record):
    """O'quvchi darsga kelmaganda ota-onaga xabar yuborish."""
    if attendance_record.status != 'ABSENT':
        return

    student = attendance_record.student
    telegram_users = TelegramUser.objects.filter(student=student, is_verified=True)
    
    message = (
        f"<b>⚠️ Davomat ma'lumoti</b>\n\n"
        f"Farzandingiz <b>{student}</b> bugungi ({attendance_record.session.date}) darsga kelmadi.\n"
        f"Guruh: {attendance_record.session.group.name}"
    )
    
    for tg_user in telegram_users:
        send_telegram_message(tg_user.telegram_id, message)


def notify_grade_added(grade_record):
    """Yangi baho qo'yilganda xabar yuborish."""
    student = grade_record.student
    telegram_users = TelegramUser.objects.filter(student=student, is_verified=True)
    
    percentage = float(grade_record.percentage)
    status = "O'tdi ✅" if percentage >= 60 else "O'tmadi ❌"
    
    message = (
        f"<b>📝 Yangi baho</b>\n\n"
        f"O'quvchi: <b>{student}</b>\n"
        f"Mavzu: {grade_record.session.title}\n"
        f"Baho: <b>{money(grade_record.percentage)}%</b>\n"
        f"Imtihon natijasi: {status}"
    )
    
    for tg_user in telegram_users:
        send_telegram_message(tg_user.telegram_id, message)


def notify_payment_received(payment_transaction):
    """To'lov qabul qilinganda xabar yuborish."""
    student = payment_transaction.student
    telegram_users = TelegramUser.objects.filter(student=student, is_verified=True)
    
    message = (
        f"<b>💰 To'lov qabul qilindi</b>\n\n"
        f"O'quvchi: <b>{student}</b>\n"
        f"Sana: {payment_transaction.payment_date}\n"
        f"Miqdor: <b>{money(payment_transaction.amount)} so'm</b>\n"
        f"To'lov turi: {payment_transaction.get_method_display()}\n\n"
        f"To'lov uchun rahmat!"
    )
    
    for tg_user in telegram_users:
        send_telegram_message(tg_user.telegram_id, message)


def notify_payment_reminder(balance):
    """To'lov muddati yaqinlashganda eslatma yuborish."""
    student = balance.student
    telegram_users = TelegramUser.objects.filter(student=student, is_verified=True)
    
    message = (
        f"<b>🔔 To'lov eslatmasi</b>\n\n"
        f"Hurmatli ota-ona, <b>{student}</b> uchun <b>{balance.group.name}</b> guruhidan "
        f"<b>{balance.month:%Y-%m}</b> oyi uchun to'lov muddati keldi.\n"
        f"Qarz miqdori: <b>{money(balance.debt_amount)} so'm</b>.\n\n"
        f"Iltimos, o'z vaqtida to'lovni amalga oshiring."
    )
    
    for tg_user in telegram_users:
        send_telegram_message(tg_user.telegram_id, message)


def notify_payment_deleted(payment_transaction):
    """To'lov o'chirilganda xabar yuborish."""
    student = payment_transaction.student
    telegram_users = TelegramUser.objects.filter(student=student, is_verified=True)
    
    message = (
        f"<b>❌ To'lov bekor qilindi</b>\n\n"
        f"O'quvchi: <b>{student}</b> uchun kiritilgan <b>{money(payment_transaction.amount)} so'm</b> miqdoridagi to'lov "
        f"({payment_transaction.payment_date}) ma'muriyat tomonidan bekor qilindi.\n\n"
        f"Agar biron bir savolingiz bo'lsa, ma'muriyatga murojaat qiling."
    )
    
    for tg_user in telegram_users:
        send_telegram_message(tg_user.telegram_id, message)


def notify_missed_attendance_to_staff(alert):
    """
    Davomat olinmagan guruh haqida Director va Administrator'larga
    Telegram xabar yuboradi.
    
    NOTE: Bu funksiya ishlashi uchun Director/Admin Telegram bot'ga ulangan bo'lishi kerak.
    Hozircha xabar tizim logiga yoziladi. Kelajakda StaffTelegramProfile modeli kerak.
    """
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
        f"ERP tizimida <b>Jarima tizimi</b> bo'limiga kiring va holat belgilang."
    )

    # Telegram xabar uchun Director/Admin ID larini topish
    # Bu yerda StaffTelegramProfile modeli mavjud bo'lsa ishlatiladi
    # Hozircha faqat log yozamiz
    try:
        from django.conf import settings
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(
            f"Missed attendance alert: {teacher_name} - {group.name} - {lesson_date}"
        )
    except Exception:
        pass

    # Agar STAFF_TELEGRAM_IDS setting mavjud bo'lsa xabar yuborish
    try:
        staff_ids = getattr(settings, 'STAFF_TELEGRAM_IDS', [])
        for telegram_id in staff_ids:
            try:
                send_telegram_message(telegram_id, message)
            except Exception:
                pass
    except Exception:
        pass
