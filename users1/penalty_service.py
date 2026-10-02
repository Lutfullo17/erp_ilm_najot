"""
Avtomatik davomat nazorat tizimi.

Dars jadvali asosida avtomatik nazorat qiladi:
1. Dars tugagandan 15 daqiqada — o'qituvchiga eslatma
2. Dars tugagandan 30 daqiqada — jarima + admin/director ga xabar

Ishga tushirish:
    python manage.py check_missed_attendance
    (har 5 daqiqada APScheduler orqali avtomatik)
"""
import datetime
import logging

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from groups_app.models import Group
from attendance.models import AttendanceSession
from users1.models import MissedAttendanceAlert, TeacherPenalty, User

logger = logging.getLogger(__name__)

REMINDER_MINUTES = 15
PENALTY_MINUTES = 30


def _get_group_end_time(group):
    """Guruhning dars tugash vaqtini qaytaradi."""
    if group.end_time:
        return group.end_time
    if group.lesson_time and group.duration:
        hours = int(group.duration)
        minutes = int((group.duration - hours) * 60)
        td = datetime.timedelta(hours=hours, minutes=minutes)
        return (datetime.datetime.combine(datetime.date.today(), group.lesson_time) + td).time()
    return None


def _send_telegram_message(chat_id, text):
    """Telegram xabar yuborish — xatolik logga yoziladi."""
    try:
        from bot.services import send_telegram_message
        return send_telegram_message(chat_id, text)
    except Exception as e:
        logger.error(f"Telegram xatolik: chat_id={chat_id}, error={e}")
        return None


def _is_today_lesson_day(group, today_name):
    """Guruhning dars kuni bugun ekanligini tekshiradi. To'g'ri match."""
    if not group.lesson_days:
        return False
    days = [d.strip() for d in group.lesson_days.split(',') if d.strip()]
    return today_name in days


def _get_admin_telegram_users():
    """Joriy botda admin akkaunti ulanmagani uchun bo'sh ro'yxat qaytaradi."""
    from bot.models import TelegramUser
    return TelegramUser.objects.none()


def _get_teacher_telegram_user(teacher):
    """Joriy botda o'qituvchi akkaunti ulanmaydi."""
    return None


def _format_lesson_time(group):
    """Dars vaqtini formatlangan ko'rinishda qaytaradi."""
    start = group.lesson_time.strftime('%H:%M') if group.lesson_time else '-'
    end = group.end_time.strftime('%H:%M') if group.end_time else '-'
    return f"{start}–{end}"


# ---------------------------------------------------------------------------
# Eslatma yuborish
# ---------------------------------------------------------------------------
def send_reminder_to_teacher(alert):
    """O'qituvchiga davomat eslatmasini yuboradi."""
    tg_user = _get_teacher_telegram_user(alert.teacher)
    if not tg_user:
        logger.warning(f"O'qituvchi Telegram'da yo'q: {alert.teacher}")
        return False

    text = (
        f"⏰ <b>Eslatma</b>\n\n"
        f"Siz hali bugungi dars uchun davomatni kiritmadingiz.\n\n"
        f"📚 Guruh: <b>{alert.group.name}</b>\n"
        f"📅 Sana: <b>{alert.lesson_date.strftime('%d.%m.%Y')}</b>\n"
        f"⏰ Vaqt: <b>{_format_lesson_time(alert.group)}</b>\n\n"
        f"Iltimos, davomatni tizimga kiriting."
    )
    result = _send_telegram_message(tg_user.telegram_id, text)
    if result:
        logger.info(f"Eslatma yuborildi: {alert.teacher}, {alert.group.name}")
    return bool(result)


# ---------------------------------------------------------------------------
# Jarima xabarlari
# ---------------------------------------------------------------------------
def _build_penalty_message(alert, penalty):
    """Jarima haqida umumiy xabar matnini yaratadi."""
    return (
        f"⚠️ <b>Davomat olinmadi</b>\n\n"
        f"O'qituvchi: <b>{alert.teacher.get_full_name() or alert.teacher.username}</b>\n"
        f"Guruh: <b>{alert.group.name}</b>\n"
        f"Dars vaqti: <b>{_format_lesson_time(alert.group)}</b>\n"
        f"Sanasi: <b>{alert.lesson_date.strftime('%d.%m.%Y')}</b>\n\n"
        f"Holat: O'qituvchi davomatni o'z vaqtida kiritmadi.\n"
        f"Jarima: <b>{abs(penalty.points)} ball</b>"
    )


def notify_admins(alert, penalty):
    """Barcha admin/director ga jarima xabarini yuboradi."""
    msg = _build_penalty_message(alert, penalty)
    recipients = _get_admin_telegram_users()
    sent = 0
    for tu in recipients:
        try:
            if _send_telegram_message(tu.telegram_id, msg):
                sent += 1
        except Exception as e:
            logger.error(f"Admin xabar xatolik: {e}")
    logger.info(f"Admin xabar: {sent}/{recipients.count()} yuborildi")


# ---------------------------------------------------------------------------
# Avtomatik jarima berish
# ---------------------------------------------------------------------------
def apply_auto_penalty(alert):
    """
    Avtomatik jarima — bir dars uchun faqat bitta.
    Transaction ichida ishlaydi, takrorlanishni bloklaydi.
    """
    if alert.penalty_applied:
        return None

    with transaction.atomic():
        # SELECT FOR UPDATE — boshqa jarayon kuta olmaydi
        locked_alert = MissedAttendanceAlert.objects.select_for_update().get(pk=alert.pk)

        if locked_alert.penalty_applied:
            return None

        penalty = TeacherPenalty.objects.create(
            teacher=alert.teacher,
            group=alert.group,
            date=alert.lesson_date,
            reason="Dars davomatini o'z vaqtida kiritmadi.",
            points=-10,
            penalty_type=TeacherPenalty.PenaltyType.ATTENDANCE_MISSED,
            is_manual=False,
        )

        locked_alert.penalty_applied = True
        locked_alert.status = MissedAttendanceAlert.Status.NOT_CAME
        locked_alert.resolved_at = timezone.now()
        locked_alert.save(update_fields=['penalty_applied', 'status', 'resolved_at'])

    logger.info(f"Auto jarima: {alert.teacher}, {alert.group.name}, -10")
    return penalty


# ---------------------------------------------------------------------------
# Asosiy nazorat sikli
# ---------------------------------------------------------------------------
def check_and_create_missed_alerts():
    """
    Har bir faol guruhni tekshiradi:
    - Dars tugaganmi?
    - Davomat olinganmi?
    - Agar olinmagan bo'lsa:
      15 daqiqada → eslatma
      30 daqiqada → jarima + xabar
    """
    today = timezone.localdate()
    now_time = timezone.localtime().time()

    days_map = {
        0: 'Dushanba', 1: 'Seshanba', 2: 'Chorshanba', 3: 'Payshanba',
        4: 'Juma', 5: 'Shanba', 6: 'Yakshanba'
    }
    today_name = days_map[today.weekday()]

    # To'xtatilgan yoki hali boshlanmagan guruhlar uchun o'qituvchi jarimalanmaydi.
    groups = Group.objects.filter(
        is_active=True,
        is_paused=False,
        teacher__isnull=False,
    ).filter(Q(start_date__isnull=True) | Q(start_date__lte=today)).select_related('teacher')

    # Shu hafta tasdiqlangan jadval o'zgarishi bugungi darsni boshqa kunga ko'chirgan bo'lsa — jarima yo'q.
    from users1.models import ScheduleChangeRequest
    week_start = today - datetime.timedelta(days=today.weekday())
    moved_away = set(
        ScheduleChangeRequest.objects.filter(
            status=ScheduleChangeRequest.Status.APPROVED,
            effective_week_start=week_start,
            old_day=today_name,
        ).exclude(new_day=today_name).values_list('group_id', flat=True)
    )

    alerts_created = 0
    reminders_sent = 0
    penalties_applied = 0

    for group in groups:
        # Bugun dars kuni ekanligini tekshirish
        if not _is_today_lesson_day(group, today_name) or group.pk in moved_away:
            continue

        end_time = _get_group_end_time(group)
        if not end_time:
            continue

        # Dars hali tugaganmi?
        if now_time < end_time:
            continue

        # Davomat olinganmi?
        if AttendanceSession.objects.filter(group=group, date=today).exists():
            continue

        # Alert yaratish (bir marta)
        alert, created = MissedAttendanceAlert.objects.get_or_create(
            teacher=group.teacher,
            group=group,
            lesson_date=today,
            defaults={'status': MissedAttendanceAlert.Status.PENDING}
        )
        if created:
            alerts_created += 1

        # Grace period
        now_dt = datetime.datetime.combine(today, now_time)
        end_dt = datetime.datetime.combine(today, end_time)
        minutes_elapsed = (now_dt - end_dt).total_seconds() / 60

        if minutes_elapsed < REMINDER_MINUTES:
            continue

        # 15–30 daqiqa: eslatma (faqat bir marta)
        if minutes_elapsed < PENALTY_MINUTES:
            if not alert.penalty_applied and not alert.resolved_at:
                if send_reminder_to_teacher(alert):
                    reminders_sent += 1
                    alert.resolved_at = timezone.now()
                    alert.save(update_fields=['resolved_at'])
            continue

        # 30+ daqiqa: avtomatik jarima
        if not alert.penalty_applied:
            penalty = apply_auto_penalty(alert)
            if penalty:
                penalties_applied += 1
                notify_admins(alert, penalty)

    return {
        'alerts_created': alerts_created,
        'reminders_sent': reminders_sent,
        'penalties_applied': penalties_applied,
    }


# ---------------------------------------------------------------------------
# Qo'lda hal qilish (Director/Dashboard)
# ---------------------------------------------------------------------------
def get_teacher_consecutive_missed_count(teacher):
    """Oxirgi ketma-ket "kelmadi" jarimalari soni.

    Zanjir o'qituvchi oradagi sanalarda davomat olgan bo'lsa (muvaffaqiyatli dars) uziladi.
    """
    alerts = list(
        MissedAttendanceAlert.objects.filter(
            teacher=teacher,
            penalty_applied=True,
            status=MissedAttendanceAlert.Status.NOT_CAME,
        ).order_by('-lesson_date')[:10]
    )
    chain = 0
    previous = None
    for alert in alerts:
        if previous is not None and AttendanceSession.objects.filter(
            teacher=teacher, date__gt=alert.lesson_date, date__lt=previous.lesson_date,
        ).exists():
            break
        chain += 1
        previous = alert
    return chain


def apply_penalty_for_alert(alert, decision, resolved_by):
    """
    Director tomonidan qo'lda hal qilish.
    Agar avtomatik jarima allaqachon berilgan bo'lsa — qayta jarima olmaydi.
    """
    if alert.penalty_applied:
        return None

    if decision == 'came':
        alert.status = MissedAttendanceAlert.Status.CAME
        penalty_points = -5
        reason = f"{alert.group.name} guruhida davomat olinmadi (darsga keldi)"
        penalty_type = TeacherPenalty.PenaltyType.ATTENDANCE_MISSED
    elif decision == 'not_came':
        alert.status = MissedAttendanceAlert.Status.NOT_CAME
        penalty_points = -10
        reason = f"{alert.group.name} guruhiga kelmadi"
        penalty_type = TeacherPenalty.PenaltyType.CLASS_SKIPPED
    else:
        raise ValueError(f"Noto'g'ri qaror: {decision}")

    with transaction.atomic():
        locked = MissedAttendanceAlert.objects.select_for_update().get(pk=alert.pk)
        if locked.penalty_applied:
            return None

        locked.status = alert.status
        locked.resolved_at = timezone.now()
        locked.resolved_by = resolved_by
        locked.penalty_applied = True
        locked.save()

        penalty = TeacherPenalty.objects.create(
            teacher=alert.teacher,
            group=alert.group,
            date=alert.lesson_date,
            reason=reason,
            points=penalty_points,
            penalty_type=penalty_type,
            is_manual=False,
            given_by=resolved_by,
        )

    # Ketma-ket tekshiruvi
    consecutive = get_teacher_consecutive_missed_count(alert.teacher)
    if decision == 'not_came' and consecutive == 3:  # zanjirning har safar emas, aynan 3-bo'g'inida bir marta
        TeacherPenalty.objects.create(
            teacher=alert.teacher,
            group=alert.group,
            date=alert.lesson_date,
            reason=f"Ketma-ket {consecutive} ta darsda davomat olinmadi",
            points=-10,
            penalty_type=TeacherPenalty.PenaltyType.CONSECUTIVE_MISSED,
            is_manual=False,
            given_by=resolved_by,
        )

    return penalty
