import logging

from django.conf import settings
from .services import send_telegram_message, money
from .models import TelegramUser

logger = logging.getLogger(__name__)


def notify_attendance_absent(attendance_record):
    """O'quvchi darsga kelmaganda ota-onaga xabar yuborish."""
    if attendance_record.status != 'ABSENT':
        return

    student = attendance_record.student
    telegram_users = TelegramUser.objects.filter(student=student, is_verified=True)
    
    message = (
        f"<b>⚠️ DAVOMAT MA'LUMOTI</b>\n"
        f"──────────────────\n"
        f"👤 O'quvchi: <b>{student}</b>\n"
        f"📅 Sana: <b>{attendance_record.session.date}</b>\n"
        f"📚 Guruh: <b>{attendance_record.session.group.name}</b>\n\n"
        f"❌ Farzandingiz bugun darsga kelmadi.\n"
        f"Iltimos, sababini ma'muriyatga ma'lum qiling."
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
        f"<b>📝 YANGI BAHO QO'YILDI</b>\n"
        f"──────────────────\n"
        f"👤 O'quvchi: <b>{student}</b>\n"
        f"📖 Mavzu: <b>{grade_record.session.title}</b>\n"
        f"📊 Natija: <code>{money(grade_record.percentage)}%</code>\n"
        f"📝 Holat: <b>{status}</b>\n\n"
        f"Farzandingizning bilim olishini qo'llab-quvvatlang! ✨"
    )
    
    for tg_user in telegram_users:
        send_telegram_message(tg_user.telegram_id, message)


def notify_payment_received(payment_transaction):
    """To'lov qabul qilinganda xabar yuborish."""
    student = payment_transaction.student
    telegram_users = TelegramUser.objects.filter(student=student, is_verified=True)
    
    message = (
        f"<b>💰 TO'LOV QABUL QILINDI</b>\n"
        f"──────────────────\n"
        f"👤 O'quvchi: <b>{student}</b>\n"
        f"📅 Sana: <b>{payment_transaction.payment_date}</b>\n"
        f"💵 Miqdor: <b>{money(payment_transaction.amount)} so'm</b>\n"
        f"💳 Usul: <b>{payment_transaction.get_method_display()}</b>\n\n"
        f"✅ To'lovingiz tasdiqlandi. Rahmat!"
    )
    
    for tg_user in telegram_users:
        send_telegram_message(tg_user.telegram_id, message)


def notify_payment_reminder(balance):
    """To'lov muddati yaqinlashganda eslatma yuborish."""
    student = balance.student
    telegram_users = TelegramUser.objects.filter(student=student, is_verified=True)
    
    message = (
        f"<b>🔔 TO'LOV UCHUN ESLATMA</b>\n"
        f"──────────────────\n"
        f"👤 O'quvchi: <b>{student}</b>\n"
        f"📚 Guruh: <b>{balance.group.name}</b>\n"
        f"📅 Oy: <b>{balance.month:%Y-%m}</b>\n"
        f"❗ Qarz miqdori: <b>{money(balance.debt_amount)} so'm</b>\n\n"
        f"⏳ Iltimos, to'lovni o'z vaqtida amalga oshiring."
    )
    
    for tg_user in telegram_users:
        send_telegram_message(tg_user.telegram_id, message)


def notify_payment_deleted(payment_transaction):
    """To'lov o'chirilganda xabar yuborish."""
    student = payment_transaction.student
    telegram_users = TelegramUser.objects.filter(student=student, is_verified=True)
    
    message = (
        f"<b>❌ TO'LOV BEKOR QILINDI</b>\n"
        f"──────────────────\n"
        f"👤 O'quvchi: <b>{student}</b>\n"
        f"📅 Sana: <b>{payment_transaction.payment_date}</b>\n"
        f"💵 Miqdor: <b><s>{money(payment_transaction.amount)} so'm</s></b>\n\n"
        f"⚠️ Ushbu to'lov ma'muriyat tomonidan bekor qilindi.\n"
        f"Savollar bo'lsa, ma'muriyatga murojaat qiling."
    )
    
    for tg_user in telegram_users:
        send_telegram_message(tg_user.telegram_id, message)


def notify_missed_attendance_to_staff(alert):
    """
    Davomat olinmagan guruh haqida Director va Administrator'larga
    Telegram xabar yuboradi.
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
        f"<b>🚨 DIQQAT: DAVOMAT OLINMADI</b>\n"
        f"──────────────────\n"
        f"📚 Guruh: <b>{group.name}</b>\n"
        f"👨‍🏫 O'qituvchi: <b>{teacher_name}</b>\n"
        f"🕐 Vaqt: <code>{time_str}</code>\n"
        f"📅 Sana: <b>{lesson_date.strftime('%d.%m.%Y')}</b>\n\n"
        f"❓ O'qituvchi darsga keldimi?\n"
        f"ERP tizimida <b>Jarima tizimi</b> bo'limiga kiring."
    )

    from users1.models import User

    # Director va Administrator larni topish
    staff_users = User.objects.filter(
        role__in=[User.Role.DIRECTOR, User.Role.ADMINISTRATOR],
        is_blocked=False,
    )

    sent = False
    for staff in staff_users:
        tg_user = TelegramUser.objects.filter(user=staff, is_verified=True).first()
        if tg_user:
            try:
                send_telegram_message(tg_user.telegram_id, message)
                sent = True
            except Exception:
                logger.exception('Failed to send missed attendance message to staff user %s', staff.pk)

    if not sent:
        staff_ids = getattr(settings, 'STAFF_TELEGRAM_IDS', [])
        if not staff_ids:
            logger.warning('No staff TelegramUser entries or STAFF_TELEGRAM_IDS configured for missed attendance notification')
        for telegram_id in staff_ids:
            try:
                send_telegram_message(telegram_id, message)
                sent = True
            except Exception:
                logger.exception('Failed to send missed attendance message to fallback telegram_id %s', telegram_id)

    return sent
