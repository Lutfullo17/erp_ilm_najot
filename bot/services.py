import json
import logging
from collections import defaultdict
from datetime import date
import decimal
from decimal import Decimal
from urllib import request as urlrequest

from django.conf import settings

from attendance.models import AttendanceRecord, AttendanceSession
from grades.models import GradeRecord
from payments.models import StudentMonthBalance, PaymentTransaction
from students.models import Student, Parent
from users1.models import User

from .models import TelegramAppeal, TelegramUser

logger = logging.getLogger(__name__)

STATE_WAITING_PHONE = 'WAITING_PHONE'
STATE_CHOOSING_CHILD = 'CHOOSING_CHILD'
STATE_CHOOSING_RECIPIENT = 'CHOOSING_RECIPIENT'
STATE_WAITING_APPEAL = 'WAITING_APPEAL'
STATE_REPLY_TO_APPEAL = 'REPLY_TO_APPEAL'

MENU_ATTENDANCE = '📊 Davomat'
MENU_GRADES = '📝 Baholar'
MENU_PAYMENTS = "💰 To'lovlar"
MENU_SCHEDULE = '📅 Jadval'
MENU_HOMEWORK = '📚 Uyga vazifa'
MENU_TOPIC = '📖 Dars mavzusi'
MENU_APPEAL = '✉️ Murojaat'
MENU_CONTACT = '📞 Aloqa'


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
        return f"{val:,.2f}".replace(',', ' ').rstrip('0').rstrip('.')
    except (ValueError, TypeError, decimal.InvalidOperation):
        return str(value)


def send_telegram_message(chat_id, text, reply_markup=None):
    if not settings.TELEGRAM_BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN topilmadi, xabar yuborilmadi.")
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
    try:
        with urlrequest.urlopen(req, timeout=10) as response:
            return json.loads(response.read().decode('utf-8'))
    except urlrequest.HTTPError as e:
        logger.error(f"Telegram xabar yuborishda HTTP xatolik: {e.code} — chat_id={chat_id}")
        return None
    except Exception as e:
        logger.error(f"Telegram xabar yuborishda xatolik: {e} — chat_id={chat_id}")
        return None


def answer_callback_query(callback_query_id, text=None):
    if not settings.TELEGRAM_BOT_TOKEN:
        return
    payload = {'callback_query_id': callback_query_id}
    if text:
        payload['text'] = text
    data = json.dumps(payload).encode('utf-8')
    req = urlrequest.Request(
        f'https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/answerCallbackQuery',
        data=data,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urlrequest.urlopen(req, timeout=10) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception as e:
        logger.error(f"answerCallbackQuery xatoligi: {e}")


def contact_keyboard():
    return {
        'keyboard': [[{'text': 'Telefon raqam yuborish', 'request_contact': True}]],
        'resize_keyboard': True,
        'one_time_keyboard': True,
    }


def main_menu_keyboard(telegram_user=None):
    keyboard = [
        [MENU_ATTENDANCE, MENU_GRADES],
        [MENU_PAYMENTS, MENU_SCHEDULE],
        [MENU_HOMEWORK, MENU_TOPIC],
    ]
    if telegram_user and telegram_user.student:
        keyboard.append([MENU_APPEAL, MENU_CONTACT])

    return {
        'keyboard': keyboard,
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


def find_students_by_phone(phone):
    """Telefon raqami bo'yicha barcha faol o'quvchilarni topadi."""
    if not phone:
        return Student.objects.none()
    digits = ''.join(ch for ch in str(phone) if ch.isdigit())
    if len(digits) < 9:
        return Student.objects.none()
    search_digits = digits[-9:]
    return Student.objects.filter(
        parent_phone__contains=search_digits,
        is_active=True,
    ).order_by('first_name', 'last_name')


def handle_start(chat_id, telegram_user=None):
    if telegram_user:
        telegram_user.state = STATE_WAITING_PHONE
        telegram_user.save(update_fields=['state', 'updated_at'])
    send_telegram_message(
        chat_id,
        'Tizimga kirish uchun telefon raqamingizni yuboring.',
        contact_keyboard(),
    )


def link_user_by_phone(telegram_user, phone):
    user = User.objects.filter(phone__contains=phone[-9:]).first()
    if user:
        telegram_user.user = user
        telegram_user.save(update_fields=['user', 'updated_at'])


def handle_child_selection(chat_id, text, telegram_user):
    """Ota-ona farzandlaridan birini tanlaydi."""
    students = find_students_by_phone(telegram_user.phone)

    # Raqam orqali tanlash
    try:
        index = int(text) - 1
        if 0 <= index < students.count():
            student = students[index]
            telegram_user.student = student
            telegram_user.is_verified = True
            telegram_user.state = ''
            telegram_user.save(update_fields=['student', 'is_verified', 'state', 'updated_at'])
            send_telegram_message(chat_id, f'Xush kelibsiz, {student}!', main_menu_keyboard(telegram_user))
            return
        else:
            send_telegram_message(chat_id, "Noto'g'ri raqam. Qaytadan tanlang.", _child_selection_keyboard(students))
            return
    except (ValueError, TypeError):
        pass

    # Emoji raqamlar orqali tanlash (1️⃣, 2️⃣, ...)
    emoji_map = {'1️⃣': 0, '2️⃣': 1, '3️⃣': 2, '4️⃣': 3, '5️⃣': 4}
    if text in emoji_map:
        index = emoji_map[text]
        if index < students.count():
            student = students[index]
            telegram_user.student = student
            telegram_user.is_verified = True
            telegram_user.state = ''
            telegram_user.save(update_fields=['student', 'is_verified', 'state', 'updated_at'])
            send_telegram_message(chat_id, f'Xush kelibsiz, {student}!', main_menu_keyboard(telegram_user))
            return

    send_telegram_message(chat_id, "Noto'g'ri tanlov. Raqam kiriting yoki tugmani bosing.", _child_selection_keyboard(students))


def _child_selection_keyboard(students):
    """Farzandlar ro'yxati uchun inline keyboard yaratadi."""
    buttons = []
    for i, student in enumerate(students, 1):
        buttons.append([{'text': f'{i}. {student}', 'callback_data': f'select_child:{student.pk}'}])

    return {
        'inline_keyboard': buttons,
    }


def handle_child_selection_callback(chat_id, data, telegram_user):
    """Inline tugma orqali farzand tanlash."""
    try:
        student_pk = int(data.split(':')[1])
    except (ValueError, IndexError):
        return

    student = Student.objects.filter(pk=student_pk, is_active=True).first()
    if not student:
        return

    # Tekshirish: bu o'quvchi haqiqatan ham shu ota-onaning farzandimi?
    students = find_students_by_phone(telegram_user.phone)
    if not students.filter(pk=student.pk).exists():
        return

    telegram_user.student = student
    telegram_user.is_verified = True
    telegram_user.state = ''
    telegram_user.save(update_fields=['student', 'is_verified', 'state', 'updated_at'])
    send_telegram_message(chat_id, f'Xush kelibsiz, {student}!', main_menu_keyboard(telegram_user))


def handle_contact(chat_id, message, telegram_user):
    contact = message.get('contact') or {}
    sender_id = (message.get('from') or {}).get('id')

    if contact.get('user_id') and contact.get('user_id') != sender_id:
        send_telegram_message(chat_id, "Iltimos, faqat o'zingizning telefon raqamingizni yuboring.", contact_keyboard())
        return

    phone = normalize_phone(contact.get('phone_number'))
    students = find_students_by_phone(phone)

    telegram_user.phone = phone
    link_user_by_phone(telegram_user, phone)

    if not students.exists():
        telegram_user.is_verified = False
        telegram_user.student = None
        telegram_user.state = ''
        telegram_user.save(update_fields=['phone', 'is_verified', 'student', 'state', 'updated_at'])
        send_telegram_message(chat_id, "Bu telefon raqam bilan o'quvchi topilmadi. Admin bilan bog'laning.", contact_keyboard())
        return

    if students.count() == 1:
        # Bitta farzand — avtomatik tanlash
        student = students.first()
        telegram_user.student = student
        telegram_user.is_verified = True
        telegram_user.state = ''
        telegram_user.save(update_fields=['phone', 'student', 'is_verified', 'state', 'updated_at'])
        send_telegram_message(chat_id, f'Xush kelibsiz, {student}!', main_menu_keyboard(telegram_user))
    else:
        # Bir nechta farzand — tanlov menyusini ko'rsatish
        telegram_user.student = None
        telegram_user.is_verified = True
        telegram_user.state = STATE_CHOOSING_CHILD
        telegram_user.save(update_fields=['phone', 'student', 'is_verified', 'state', 'updated_at'])
        child_list = '\n'.join([f"{i}. {s}" for i, s in enumerate(students, 1)])
        text = (
            f"<b>👤 Sizning farzandlaringiz:</b>\n"
            f"──────────────────\n"
            f"{child_list}\n\n"
            f"Farzandni tanlang — raqamini kiriting yoki quyidagi tugmalardan birini bosing:"
        )
        send_telegram_message(chat_id, text, _child_selection_keyboard(students))


def handle_phone_text(chat_id, text, telegram_user):
    phone = normalize_phone(text)
    if len(phone) != 12 or not phone.startswith('998'):
        send_telegram_message(chat_id, "Noto'g'ri telefon raqam. Namuna: 901234567 yoki +998901234567", contact_keyboard())
        return

    students = find_students_by_phone(phone)

    telegram_user.phone = phone
    link_user_by_phone(telegram_user, phone)

    if not students.exists():
        telegram_user.is_verified = False
        telegram_user.student = None
        telegram_user.state = ''
        telegram_user.save(update_fields=['phone', 'is_verified', 'student', 'state', 'updated_at'])
        send_telegram_message(chat_id, "Bu telefon raqam bilan o'quvchi topilmadi. Admin bilan bog'laning.", contact_keyboard())
        return

    if students.count() == 1:
        student = students.first()
        telegram_user.student = student
        telegram_user.is_verified = True
        telegram_user.state = ''
        telegram_user.save(update_fields=['phone', 'student', 'is_verified', 'state', 'updated_at'])
        send_telegram_message(chat_id, f'Xush kelibsiz, {student}!', main_menu_keyboard(telegram_user))
    else:
        telegram_user.student = None
        telegram_user.is_verified = True
        telegram_user.state = STATE_CHOOSING_CHILD
        telegram_user.save(update_fields=['phone', 'student', 'is_verified', 'state', 'updated_at'])
        child_list = '\n'.join([f"{i}. {s}" for i, s in enumerate(students, 1)])
        text_msg = (
            f"<b>👤 Sizning farzandlaringiz:</b>\n"
            f"──────────────────\n"
            f"{child_list}\n\n"
            f"Farzandni tanlang — raqamini kiriting yoki quyidagi tugmalardan birini bosing:"
        )
        send_telegram_message(chat_id, text_msg, _child_selection_keyboard(students))


def require_verified(chat_id, telegram_user):
    if telegram_user.is_verified and telegram_user.student_id:
        return True
    handle_start(chat_id, telegram_user)
    return False


def attendance_text(student):
    records = AttendanceRecord.objects.filter(student=student).select_related('session', 'session__group')[:10]
    if not records:
        return "Davomat ma'lumotlari hali yo'q."

    status_map = {
        'PRESENT': '✅ Keldi',
        'ABSENT': '❌ Kelmadi',
        'EXCUSED': '🟡 Sababli',
        'LATE': '⏳ Kechikdi',
    }

    present_count = sum(1 for r in records if r.status == 'PRESENT')
    absent_count = sum(1 for r in records if r.status == 'ABSENT')

    lines = [
        "<b>📊 OXIRGI DAVOMATLAR</b>",
        "──────────────────",
        f"✅ Keldi: <b>{present_count}</b>  |  ❌ Kelmadi: <b>{absent_count}</b>\n",
    ]

    grouped = defaultdict(list)
    for record in records:
        grouped[record.session.date].append(record)

    for day_date, day_records in grouped.items():
        lines.append(f"📅 <b>{day_date:%d.%m.%Y}</b>")
        for record in day_records:
            status_text = status_map.get(record.status, record.get_status_display())
            lines.append(f"  • <code>{record.session.group.name:<12}</code> — {status_text}")
        lines.append("")

    return '\n'.join(lines).strip()


def grades_text(student):
    records = GradeRecord.objects.filter(student=student).select_related('session', 'session__group')[:10]
    if not records:
        return "Baho ma'lumotlari hali yo'q."

    passed = sum(1 for r in records if float(r.percentage) >= 60)
    failed = len(records) - passed

    lines = [
        "<b>📝 OXIRGI BAHOLAR</b>",
        "──────────────────",
        f"✅ O'tdi: <b>{passed}</b>  |  ❌ O'tmadi: <b>{failed}</b>\n",
    ]

    grouped = defaultdict(list)
    for record in records:
        grouped[record.session.date].append(record)

    for day_date, day_records in grouped.items():
        lines.append(f"📅 <b>{day_date:%d.%m.%Y}</b>")
        for record in day_records:
            pct = float(record.percentage)
            emoji = "✅" if pct >= 60 else "❌"
            percentage_str = money(record.percentage)
            lines.append(
                f"  • <code>{record.session.group.name:<12}</code>\n"
                f"    {emoji} <b>{percentage_str}%</b> — <i>{record.session.title}</i>"
            )
        lines.append("")

    return '\n'.join(lines).strip()


def payments_text(student):
    # To'lov tranzaksiyalarini olish
    payments = PaymentTransaction.objects.filter(
        student=student
    ).select_related('group').order_by('-payment_date')[:15]

    # Barcha qarzli balanslarni olish (admindagidek jami qarz)
    debt_balances = StudentMonthBalance.objects.filter(
        student=student,
    ).select_related('group').order_by('-month')
    debt_balances = [b for b in debt_balances if b.debt_amount > 0]

    total_debt = sum(float(b.debt_amount) for b in debt_balances)

    lines = [
        "<b>💰 TO'LOV TARIXI</b>",
        "──────────────────\n",
    ]

    # To'langanlar ro'yxati
    if payments:
        lines.append("<b>✅ TO'LANGANLAR:</b>")
        for p in payments:
            date_str = p.payment_date.strftime('%d.%m.%Y') if p.payment_date else '---'
            lines.append(f"  💵 <code>{money(p.amount)}</code> so'm")
            lines.append(f"     📅 <i>{date_str}</i> — <code>{p.group.name}</code>")
        lines.append("")

    # Qarzlar ro'yxati
    if debt_balances:
        lines.append("<b>❗ JAMI QARZ: <code>{}</code> so'm</b>".format(money(total_debt)))
        lines.append("")
        for b in debt_balances:
            month_str = b.month.strftime('%Y-yil, %m-oy') if b.month else '---'
            lines.append(f"  ❌ <code>{money(b.debt_amount)}</code> so'm")
            lines.append(f"     📅 <i>{month_str}</i> — <code>{b.group.name}</code>")
        lines.append("")

    return '\n'.join(lines).strip()


def schedule_text(student):
    groups = student.groups.filter(groupstudent__is_active=True, is_active=True).distinct()
    if not groups:
        return "Jadval uchun faol guruh topilmadi."

    lines = [
        "<b>📅 DARS JADVALI</b>",
        "──────────────────",
        f"📚 Faol guruhlar: <b>{groups.count()}</b>\n",
    ]

    for group in groups:
        days = group.lesson_days or '---'
        time_str = group.lesson_time.strftime('%H:%M') if group.lesson_time else '---'
        end_time = group.end_time.strftime('%H:%M') if group.end_time else ''
        time_display = f"{time_str}" + (f" - {end_time}" if end_time else "")

        lines.append(f"📖 <b>{group.name}</b>")
        lines.append(f"  ├  🗓 Kunlari: <code>{days}</code>")
        lines.append(f"  ├  ⏰ Vaqti: <code>{time_display}</code>")
        lines.append(f"  └  📍 Xonasi: <code>{group.get_room_display()}</code>")
        lines.append("")

    return '\n'.join(lines).strip()


def homework_text(student):
    sessions = AttendanceSession.objects.filter(
        group__students=student,
        group__groupstudent__is_active=True
    ).exclude(homework='').order_by('-date', '-created_at')[:5]

    if not sessions:
        return "Hozircha uyga vazifa ma'lumotlari yo'q."

    lines = [
        "<b>📚 OXIRGI UYGA VAZIFALAR</b>",
        "──────────────────\n"
    ]

    grouped = defaultdict(list)
    for session in sessions:
        grouped[session.date].append(session)

    for day_date, day_sessions in grouped.items():
        lines.append(f"📅 <b>{day_date:%d.%m.%Y}</b>")
        for session in day_sessions:
            lines.append(f"  • <code>{session.group.name}</code>")
            lines.append(f"    <i>{session.homework}</i>")
        lines.append("")

    return '\n'.join(lines).strip()


def topic_text(student):
    sessions = AttendanceSession.objects.filter(
        group__students=student,
        group__groupstudent__is_active=True
    ).exclude(lesson_topic='').order_by('-date', '-created_at')[:5]

    if not sessions:
        return "Hozircha o'tilgan darslar haqida ma'lumot yo'q."

    lines = [
        "<b>📖 O'TILGAN DARS MAVZULARI</b>",
        "──────────────────\n"
    ]

    grouped = defaultdict(list)
    for session in sessions:
        grouped[session.date].append(session)

    for day_date, day_sessions in grouped.items():
        lines.append(f"📅 <b>{day_date:%d.%m.%Y}</b>")
        for session in day_sessions:
            lines.append(f"  • <code>{session.group.name}</code>")
            lines.append(f"    <i>{session.lesson_topic}</i>")
        lines.append("")

    return '\n'.join(lines).strip()


def handle_menu(chat_id, text, telegram_user):
    student = telegram_user.student

    if text == MENU_ATTENDANCE:
        send_telegram_message(chat_id, attendance_text(student), main_menu_keyboard(telegram_user))
    elif text == MENU_GRADES:
        send_telegram_message(chat_id, grades_text(student), main_menu_keyboard(telegram_user))
    elif text == MENU_PAYMENTS:
        send_telegram_message(chat_id, payments_text(student), main_menu_keyboard(telegram_user))
    elif text == MENU_SCHEDULE:
        send_telegram_message(chat_id, schedule_text(student), main_menu_keyboard(telegram_user))
    elif text == MENU_HOMEWORK:
        send_telegram_message(chat_id, homework_text(student), main_menu_keyboard(telegram_user))
    elif text == MENU_TOPIC:
        send_telegram_message(chat_id, topic_text(student), main_menu_keyboard(telegram_user))
    elif text == MENU_CONTACT:
        contact_info = (
            "<b>📞 ALOQA MA'LUMOTLARI</b>\n"
            "──────────────────\n"
            "📍 <b>Manzil:</b> Urgut tumani, Quyi Tegana \n"
            "📞 <b>Telefon:</b> +998 93 331 44 74\n"
            "🌐 <b>Telegram:</b> @Quvonchbek474\n\n"
            "🌐 <b>Telegram Kanal:</b> @ilm_najotedu\n\n"
            "Ish vaqtimiz: 08:00 - 19:00"
        )
        send_telegram_message(chat_id, contact_info, main_menu_keyboard(telegram_user))
    elif text == MENU_APPEAL:
        if not telegram_user.student:
            send_telegram_message(chat_id, "Faqat o'quvchilar murojaat yubora oladi.", main_menu_keyboard(telegram_user))
            return
        telegram_user.state = STATE_CHOOSING_RECIPIENT
        telegram_user.save(update_fields=['state', 'updated_at'])
        choose_recipient_keyboard = {
            'inline_keyboard': [
                [
                    {'text': '👨‍💼 Adminga', 'callback_data': 'appeal_to:ADMIN'},
                    {'text': "👨‍🏫 O'qituvchiga", 'callback_data': 'appeal_to:TEACHER'},
                ],
            ],
        }
        send_telegram_message(chat_id, "Murojaatni kimga yubormoqchisiz?", choose_recipient_keyboard)
    elif text == '🔄 Boshqa farzandni tanlash':
        # Farzandni o'zgartirish
        students = find_students_by_phone(telegram_user.phone)
        if students.count() <= 1:
            send_telegram_message(chat_id, "Sizda bitta farzand bor.", main_menu_keyboard(telegram_user))
            return
        telegram_user.student = None
        telegram_user.state = STATE_CHOOSING_CHILD
        telegram_user.save(update_fields=['student', 'state', 'updated_at'])
        child_list = '\n'.join([f"{i}. {s}" for i, s in enumerate(students, 1)])
        text_msg = (
            f"<b>👤 Sizning farzandlaringiz:</b>\n"
            f"──────────────────\n"
            f"{child_list}\n\n"
            f"Farzandni tanlang:"
        )
        send_telegram_message(chat_id, text_msg, _child_selection_keyboard(students))
    else:
        send_telegram_message(chat_id, "Menyudan birini tanlang.", main_menu_keyboard(telegram_user))


def handle_appeal(chat_id, text, telegram_user):
    message = str(text or '').strip()
    if len(message) < 3:
        send_telegram_message(chat_id, "Murojaat matni juda qisqa. Iltimos, batafsilroq yozing.")
        return

    recipient_type = telegram_user.state.replace(STATE_WAITING_APPEAL + ':', '')
    telegram_user.state = ''
    telegram_user.save(update_fields=['state', 'updated_at'])

    sender_type = get_sender_type(telegram_user)
    TelegramAppeal.objects.create(
        telegram_user=telegram_user,
        student=telegram_user.student,
        message=message,
        sender_type=sender_type,
        recipient_type=recipient_type,
    )
    send_telegram_message(chat_id, 'Murojaatingiz qabul qilindi. Tez orada sizga javob beramiz.', main_menu_keyboard(telegram_user))

    # Adminga sodda ko'rinishda xabar yuborish
    staff_users = TelegramUser.objects.filter(
        user__role__in=[User.Role.DIRECTOR, User.Role.ADMINISTRATOR, User.Role.TEACHER],
        is_verified=True,
    ).exclude(telegram_id=chat_id)

    student_name = str(telegram_user.student) if telegram_user.student else "Noma'lum"

    for staff in staff_users:
        try:
            appeal_notification = (
                f"<b>✉️ YANGI MUROJAAT</b>\n"
                f"──────────────────\n"
                f"👤 <b>O'quvchi:</b> {student_name}\n"
                f"📝 <b>Xabar:</b>\n{message}\n\n"
                f"Javob berish uchun tizimga kiring."
            )
            send_telegram_message(staff.telegram_id, appeal_notification)
        except Exception as e:
            logger.error(f"Staff xabar yuborishda xatolik: {e}")


def get_sender_type(telegram_user):
    if telegram_user.user:
        if telegram_user.user.is_admin_access:
            return TelegramAppeal.SenderType.ADMIN
        elif telegram_user.user.is_teacher:
            return TelegramAppeal.SenderType.TEACHER
    return TelegramAppeal.SenderType.STUDENT


STATE_REPLY_TARGET = {}  # chat_id -> {target_id, recipient_label}


def handle_reply_to_appeal(chat_id, text, telegram_user):
    """Admin/O'qituvchi o'quvchiga javob yozganda."""
    target = STATE_REPLY_TARGET.get(chat_id)
    if not target:
        send_telegram_message(chat_id, "Xatolik: javob berilishi kerak bo'lgan murojaat topilmadi.")
        telegram_user.state = ''
        telegram_user.save(update_fields=['state', 'updated_at'])
        return

    target_id = target['target_id']
    staff_name = target.get('staff_name', 'Admin')

    if telegram_user.user and telegram_user.user.role == User.Role.TEACHER:
        sender_label = "O'qituvchi"
    else:
        sender_label = "Admin"

    appeal_msg = (
        f"<b>💬 JAVOB KELDI!</b>\n"
        f"──────────────────\n"
        f"👤 <b>Yuboruvchi:</b> {sender_label}\n\n"
        f"{text}"
    )
    send_telegram_message(target_id, appeal_msg, main_menu_keyboard())
    send_telegram_message(chat_id, 'Javob yuborildi.', main_menu_keyboard(telegram_user))
    STATE_REPLY_TARGET.pop(chat_id, None)
    telegram_user.state = ''
    telegram_user.save(update_fields=['state', 'updated_at'])


def handle_callback_query(callback_query):
    """Inline tugmalar bosilganda ishlaydi."""
    query_id = callback_query.get('id')
    data = callback_query.get('data', '')
    from_chat = callback_query.get('message', {}).get('chat', {}).get('id')
    sender = callback_query.get('from', {})
    sender_id = sender.get('id')

    if not from_chat:
        return

    telegram_user = TelegramUser.objects.filter(telegram_id=sender_id).select_related('user').first()

    if not telegram_user:
        answer_callback_query(query_id, "Foydalanuvchi topilmadi.")
        return

    # Farzand tanlash (inline tugma)
    if data.startswith('select_child:'):
        handle_child_selection_callback(from_chat, data, telegram_user)
        answer_callback_query(query_id, "Tanlandi.")
        return

    # O'quvchi "Adminga" yoki "O'qituvchiga" tugmasini bosganda
    if data.startswith('appeal_to:'):
        if not telegram_user.is_verified:
            answer_callback_query(query_id, "Avval tizimga kiring.")
            return

        recipient_type = data.split(':', 1)[1]
        telegram_user.state = f'{STATE_WAITING_APPEAL}:{recipient_type}'
        telegram_user.save(update_fields=['state', 'updated_at'])
        answer_callback_query(query_id, "Murojaatingizni yozing.")
        send_telegram_message(from_chat, "Murojaatingizni yozib yuboring:")
        return

    # Faqat admin/teacher foydalanuvchilar javob bera oladi
    if not telegram_user.user:
        answer_callback_query(query_id, "Sizda ruxsat yo'q.")
        return

    is_staff = telegram_user.user.is_admin_access or telegram_user.user.is_teacher
    if not is_staff:
        answer_callback_query(query_id, "Sizda ruxsat yo'q.")
        return


def handle_update(update):
    callback_query = update.get('callback_query')
    if callback_query:
        handle_callback_query(callback_query)
        return

    message = update.get('message')
    if not message:
        return

    chat_id = (message.get('chat') or {}).get('id')
    if not chat_id:
        return

    telegram_user = get_or_create_telegram_user(message)
    text = (message.get('text') or '').strip()

    if text == '/start':
        handle_start(chat_id, telegram_user)
        return

    if message.get('contact'):
        handle_contact(chat_id, message, telegram_user)
        return

    if telegram_user.state == STATE_WAITING_PHONE and text and any(c.isdigit() for c in text):
        handle_phone_text(chat_id, text, telegram_user)
        return

    if not require_verified(chat_id, telegram_user):
        return

    # Farzand tanlash holati
    if telegram_user.state == STATE_CHOOSING_CHILD:
        handle_child_selection(chat_id, text, telegram_user)
        return

    if telegram_user.state == STATE_REPLY_TO_APPEAL:
        handle_reply_to_appeal(chat_id, text, telegram_user)
        return

    if telegram_user.state and telegram_user.state.startswith(STATE_WAITING_APPEAL):
        handle_appeal(chat_id, text, telegram_user)
        return

    handle_menu(chat_id, text, telegram_user)
