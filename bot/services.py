import json
from datetime import date
import decimal
from decimal import Decimal
from urllib import request as urlrequest

from django.conf import settings

from attendance.models import AttendanceRecord
from grades.models import GradeRecord
from payments.models import StudentMonthBalance
from students.models import Student

from .models import TelegramAppeal, TelegramUser


STATE_WAITING_APPEAL = 'WAITING_APPEAL'

MENU_ATTENDANCE = '📊 Davomat'
MENU_GRADES = '📝 Baholar'
MENU_PAYMENTS = "💰 To'lovlar"
MENU_SCHEDULE = '📅 Jadval'
MENU_APPEAL = '✉️ Murojaat'


def normalize_phone(value):
    digits = ''.join(ch for ch in str(value or '') if ch.isdigit())
    if len(digits) == 9:
        digits = '998' + digits
    return digits


def money(value):
    if value is None:
        return '0'
    try:
        val = Decimal(str(value))
        if val == val.to_integral():
            return f"{int(val):,}".replace(',', ' ')
        # Agarda tiyinlar bo'lsa, 2 tagacha ko'rsatiladi va ortiqcha nol olib tashlanadi
        return f"{val:,.2f}".replace(',', ' ').rstrip('0').rstrip('.')
    except (ValueError, TypeError, decimal.InvalidOperation):
        return str(value)


def send_telegram_message(chat_id, text, reply_markup=None):
    if not settings.TELEGRAM_BOT_TOKEN:
        return None

    payload = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'HTML',
    }
    if reply_markup:
        payload['reply_markup'] = reply_markup

    data = json.dumps(payload).encode('utf-8')
    req = urlrequest.Request(
        f'https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage',
        data=data,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    with urlrequest.urlopen(req, timeout=10) as response:
        return json.loads(response.read().decode('utf-8'))


def contact_keyboard():
    return {
        'keyboard': [[{'text': 'Telefon raqam yuborish', 'request_contact': True}]],
        'resize_keyboard': True,
        'one_time_keyboard': True,
    }


def main_menu_keyboard():
    return {
        'keyboard': [
            [MENU_ATTENDANCE, MENU_GRADES],
            [MENU_PAYMENTS, MENU_SCHEDULE],
            [MENU_APPEAL],
        ],
        'resize_keyboard': True,
    }


def get_or_create_telegram_user(message):
    sender = message.get('from') or {}
    telegram_user, _ = TelegramUser.objects.get_or_create(
        telegram_id=sender.get('id'),
        defaults={
            'username': sender.get('username', ''),
            'first_name': sender.get('first_name', ''),
        },
    )
    telegram_user.username = sender.get('username', telegram_user.username) or ''
    telegram_user.first_name = sender.get('first_name', telegram_user.first_name) or ''
    telegram_user.save(update_fields=['username', 'first_name', 'updated_at'])
    return telegram_user


def handle_start(chat_id):
    send_telegram_message(
        chat_id,
        'Tizimga kirish uchun telefon raqamingizni yuboring.',
        contact_keyboard(),
    )


def handle_contact(chat_id, message, telegram_user):
    contact = message.get('contact') or {}
    sender_id = (message.get('from') or {}).get('id')

    if contact.get('user_id') and contact.get('user_id') != sender_id:
        send_telegram_message(chat_id, "Iltimos, faqat o'zingizning telefon raqamingizni yuboring.", contact_keyboard())
        return

    phone = normalize_phone(contact.get('phone_number'))
    student = Student.objects.filter(phone__contains=phone[-9:], is_active=True).first()
    if not student:
        telegram_user.phone = phone
        telegram_user.is_verified = False
        telegram_user.student = None
        telegram_user.save(update_fields=['phone', 'is_verified', 'student', 'updated_at'])
        send_telegram_message(chat_id, "Bu telefon raqam bilan o'quvchi topilmadi. Admin bilan bog'laning.", contact_keyboard())
        return

    telegram_user.phone = phone
    telegram_user.student = student
    telegram_user.is_verified = True
    telegram_user.state = ''
    telegram_user.save(update_fields=['phone', 'student', 'is_verified', 'state', 'updated_at'])
    send_telegram_message(chat_id, f'Xush kelibsiz, {student}!', main_menu_keyboard())


def require_verified(chat_id, telegram_user):
    if telegram_user.is_verified and telegram_user.student_id:
        return True
    handle_start(chat_id)
    return False


def attendance_text(student):
    records = AttendanceRecord.objects.filter(student=student).select_related('session', 'session__group')[:10]
    if not records:
        return "Davomat ma'lumotlari hali yo'q."

    lines = ['Oxirgi davomatlar:']
    for record in records:
        lines.append(f'{record.session.date:%Y-%m-%d} | {record.session.group.name} | {record.get_status_display()}')
    return '\n'.join(lines)


def grades_text(student):
    records = GradeRecord.objects.filter(student=student).select_related('session', 'session__group')[:10]
    if not records:
        return "Baho ma'lumotlari hali yo'q."

    lines = ['Oxirgi baholar:']
    for record in records:
        lines.append(f'{record.session.date:%Y-%m-%d} | {record.session.title} | {money(record.percentage)}%')
    return '\n'.join(lines)


def payments_text(student):
    balances = StudentMonthBalance.objects.filter(student=student).select_related('group')[:12]
    if not balances:
        return "To'lov ma'lumotlari hali yo'q."

    lines = ["To'lovlar:"]
    for balance in balances:
        lines.append(
            f'{balance.month:%Y-%m} | {balance.group.name} | {balance.get_status_display()} | '
            f"To'langan: {money(balance.paid_amount)} | Qarz: {money(balance.debt_amount)}"
        )
    return '\n'.join(lines)


def schedule_text(student):
    groups = student.groups.filter(groupstudent__is_active=True, is_active=True).distinct()
    if not groups:
        return "Jadval uchun faol guruh topilmadi."

    lines = ['Guruhlaringiz:']
    for group in groups:
        lines.append(f'{group.name} | Oylik: {money(group.monthly_fee)}')
    return '\n'.join(lines)


def handle_menu(chat_id, text, telegram_user):
    student = telegram_user.student

    if text == MENU_ATTENDANCE:
        send_telegram_message(chat_id, attendance_text(student), main_menu_keyboard())
    elif text == MENU_GRADES:
        send_telegram_message(chat_id, grades_text(student), main_menu_keyboard())
    elif text == MENU_PAYMENTS:
        send_telegram_message(chat_id, payments_text(student), main_menu_keyboard())
    elif text == MENU_SCHEDULE:
        send_telegram_message(chat_id, schedule_text(student), main_menu_keyboard())
    elif text == MENU_APPEAL:
        telegram_user.state = STATE_WAITING_APPEAL
        telegram_user.save(update_fields=['state', 'updated_at'])
        send_telegram_message(chat_id, 'Murojaatingizni yozib yuboring.')
    else:
        send_telegram_message(chat_id, 'Menyudan birini tanlang.', main_menu_keyboard())


def handle_appeal(chat_id, text, telegram_user):
    message = str(text or '').strip()
    if len(message) < 3:
        send_telegram_message(chat_id, "Murojaat matni juda qisqa. Iltimos, batafsilroq yozing.")
        return

    TelegramAppeal.objects.create(
        telegram_user=telegram_user,
        student=telegram_user.student,
        message=message,
    )
    telegram_user.state = ''
    telegram_user.save(update_fields=['state', 'updated_at'])
    send_telegram_message(chat_id, 'Murojaatingiz qabul qilindi.', main_menu_keyboard())


def handle_update(update):
    message = update.get('message')
    if not message:
        return

    chat_id = (message.get('chat') or {}).get('id')
    if not chat_id:
        return

    telegram_user = get_or_create_telegram_user(message)
    text = (message.get('text') or '').strip()

    if text == '/start':
        handle_start(chat_id)
        return

    if message.get('contact'):
        handle_contact(chat_id, message, telegram_user)
        return

    if not require_verified(chat_id, telegram_user):
        return

    if telegram_user.state == STATE_WAITING_APPEAL:
        handle_appeal(chat_id, text, telegram_user)
        return

    handle_menu(chat_id, text, telegram_user)
