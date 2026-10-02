"""Boshqaruv bildirishnomalari (davomat, jarima ogohlantirishlari, jadval arizalari, tug'ilgan kunlar).

Avval bular Boshqaruv panelining tepasida chiqardi va asosiy statistikani pastga surib yuborardi.
Endi alohida "Bildirishnomalar" sahifasida ko'rsatiladi, menyuda esa soni belgi (badge) sifatida chiqadi.
"""
from django.db.models import Count, Q
from django.utils import timezone

DAY_NAMES = {
    0: 'Dushanba', 1: 'Seshanba', 2: 'Chorshanba', 3: 'Payshanba',
    4: 'Juma', 5: 'Shanba', 6: 'Yakshanba',
}


def missing_attendance_groups(now=None):
    """Bugun darsi tugagan, lekin davomati olinmagan faol guruhlar."""
    from attendance.models import AttendanceSession
    from groups_app.models import Group

    now = timezone.localtime(now)
    today = now.date()
    groups = list(
        Group.objects.filter(
            is_active=True, is_paused=False,
            lesson_days__contains=DAY_NAMES[today.weekday()],
            end_time__lt=now.time(),
        ).select_related('teacher').order_by('lesson_time', 'name')
    )
    done = set(
        AttendanceSession.objects.filter(group__in=groups, date=today).values_list('group_id', flat=True)
    )
    return [g for g in groups if g.id not in done]


def teachers_with_repeated_misses():
    """Kamida 3 marta "darsga kelmadi" deb jarimalangan o'qituvchilar (bitta so'rov bilan)."""
    from .models import MissedAttendanceAlert, User

    return list(
        User.objects.filter(role=User.Role.TEACHER, is_deleted=False)
        .annotate(missed=Count('missed_alerts', filter=Q(
            missed_alerts__status=MissedAttendanceAlert.Status.NOT_CAME,
            missed_alerts__penalty_applied=True,
        )))
        .filter(missed__gte=3)
        .order_by('first_name', 'last_name')
    )


def notification_count(user):
    """Menyudagi belgi uchun: hal qilinishi kerak bo'lgan holatlar soni (arzon so'rovlar)."""
    if not getattr(user, 'is_authenticated', False) or not getattr(user, 'is_admin_access', False):
        return 0
    from .models import MissedAttendanceAlert, ScheduleChangeRequest

    return (
        len(missing_attendance_groups())
        + MissedAttendanceAlert.objects.filter(status=MissedAttendanceAlert.Status.PENDING).count()
        + ScheduleChangeRequest.objects.filter(status=ScheduleChangeRequest.Status.PENDING).count()
    )


def notifications_context(request):
    """Context processor: har bir sahifada menyu belgisi uchun `notification_count`."""
    user = getattr(request, 'user', None)
    if user is None or not getattr(user, 'is_authenticated', False) or not getattr(user, 'is_admin_access', False):
        return {}
    try:
        return {'notification_count': notification_count(user)}
    except Exception:
        return {}
