"""
Avtomatik davomat ogohlantirish va jarima tizimi.
Bu modul attendance app signals bilan birgalikda ishlaydi.

Management command yoki scheduler orqali chaqirilishi kerak:
    python manage.py check_missed_attendance
"""
from django.utils import timezone

from groups_app.models import Group
from attendance.models import AttendanceSession
from users1.models import MissedAttendanceAlert, TeacherPenalty, User


def check_and_create_missed_alerts():
    """
    Dars vaqti o'tgan, lekin davomat olinmagan guruhlar uchun
    MissedAttendanceAlert yaratadi va xabar yuboradi.
    """
    today = timezone.localdate()
    now_time = timezone.localtime().time()

    days_map = {
        0: 'Dushanba', 1: 'Seshanba', 2: 'Chorshanba', 3: 'Payshanba',
        4: 'Juma', 5: 'Shanba', 6: 'Yakshanba'
    }
    today_name = days_map[today.weekday()]

    # Bugun dars bo'lgan va vaqti o'tgan, lekin davomat olinmagan guruhlar
    groups_with_missed = Group.objects.filter(
        is_active=True,
        lesson_days__contains=today_name,
        end_time__lt=now_time,
        teacher__isnull=False,
    ).select_related('teacher')

    created_count = 0
    for group in groups_with_missed:
        # Davomat olinganmi?
        has_session = AttendanceSession.objects.filter(
            group=group,
            date=today,
        ).exists()

        if not has_session:
            # MissedAttendanceAlert yaratish (agar mavjud bo'lmasa)
            alert, created = MissedAttendanceAlert.objects.get_or_create(
                teacher=group.teacher,
                group=group,
                lesson_date=today,
                defaults={'status': MissedAttendanceAlert.Status.PENDING}
            )
            if created:
                created_count += 1
                # Xabar yuborish
                try:
                    notify_staff_about_missed_attendance(alert)
                except Exception:
                    pass

    return created_count


def notify_staff_about_missed_attendance(alert):
    """
    Director va Administrator'larga Telegram xabar yuboradi
    davomat olinmagan guruh haqida.
    """
    try:
        from bot.notifications import notify_missed_attendance_to_staff
        notify_missed_attendance_to_staff(alert)
    except Exception:
        pass


def get_teacher_consecutive_missed_count(teacher):
    """Teacher ketma-ket necha marta davomat olmagan sanaydi"""
    recent = MissedAttendanceAlert.objects.filter(
        teacher=teacher,
        penalty_applied=True,
    ).order_by('-lesson_date')[:5]

    count = 0
    for alert in recent:
        if alert.status in [
            MissedAttendanceAlert.Status.CAME,
            MissedAttendanceAlert.Status.NOT_CAME,
        ]:
            count += 1
        else:
            break
    return count


def apply_penalty_for_alert(alert, decision, resolved_by):
    """
    Alert hal qilinganda jarima beradi.
    decision: 'came' (keldi, davomat olmadi → -5)
              'not_came' (kelmadi → -10)
    
    Returns: TeacherPenalty instance
    """
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

    alert.resolved_at = timezone.now()
    alert.resolved_by = resolved_by
    alert.penalty_applied = True
    alert.save()

    # Asosiy jarima
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

    # Ketma-ket jarima tekshiruvi
    consecutive = get_teacher_consecutive_missed_count(alert.teacher)
    if consecutive >= 2:
        TeacherPenalty.objects.create(
            teacher=alert.teacher,
            group=alert.group,
            date=alert.lesson_date,
            reason=f"Ketma-ket {consecutive + 1} ta darsda davomat yoki darsga kelmadi",
            points=-10,
            penalty_type=TeacherPenalty.PenaltyType.CONSECUTIVE_MISSED,
            is_manual=False,
            given_by=resolved_by,
        )

    return penalty
