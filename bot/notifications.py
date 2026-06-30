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
    status = "O'tdi ✅" if percentage >= 60 else "O'tmadi ❌" # Exam pass/fail logic
    
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
