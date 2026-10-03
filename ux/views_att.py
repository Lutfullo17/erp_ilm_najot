import datetime

from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from attendance.models import AttendanceRecord, AttendanceSession, AttendanceStatus, LessonPlan
from groups_app.models import Group
from users1.models import AuditLog

from . import services
from .base import UxView, json_body, ux_login
from .nav import role_of

EARLY_MINUTES = 15  # B10: o'qituvchi davomatni dars boshlanishidan 15 daqiqa oldin ocha oladi


def group_for(user, gid):
    group = get_object_or_404(Group.objects.select_related('teacher'), pk=gid)
    if role_of(user) == 'teacher' and group.teacher_id != user.pk:
        return None
    return group


def check_window(user, group, date, now):
    """Davomat olish mumkinmi? (ok, kod, xabar). Administrator/direktor uchun cheklov yo'q (kelajak sanadan tashqari)."""
    today = now.date()
    if date > today:
        return False, 'future', "Kelajakdagi sana uchun davomat olib bo'lmaydi."
    if role_of(user) != 'teacher':
        return True, '', ''
    if date != today:
        return False, 'past', "O'tgan kun davomatini faqat administrator tuzata oladi."
    names = {d.strip() for d in (group.lesson_days or '').split(',') if d.strip()}
    if services.DAY_NAMES[today.weekday()] not in names:
        return False, 'not_day', "Bugun bu guruhning dars kuni emas."
    end = services.lesson_end(group)
    if not group.lesson_time or not end:
        return False, 'no_time', "Guruhning dars vaqti belgilanmagan. Administratorga murojaat qiling."
    start_dt = datetime.datetime.combine(today, group.lesson_time) - datetime.timedelta(minutes=EARLY_MINUTES)
    now_naive = now.replace(tzinfo=None)
    if now_naive < start_dt:
        return False, 'early', f"Dars hali boshlanmagan. Davomatni {group.lesson_time.strftime('%H:%M')} dan {EARLY_MINUTES} daqiqa oldin boshlash mumkin."
    if now.time() > end and not AttendanceSession.objects.filter(group=group, date=today).exists():
        return False, 'late', "Davomat vaqtida olinmadi. Tiklash uchun administratorga murojaat qiling."
    return True, '', ''


def parse_date(value, default):
    try:
        return datetime.date.fromisoformat(value)
    except (TypeError, ValueError):
        return default


class AttendanceListView(UxView):
    template_name = 'new/attendance_list.html'

    def get(self, request):
        teacher = request.user if role_of(request.user) == 'teacher' else None
        lessons = services.lessons_today(teacher=teacher)
        ctx = {'lessons': lessons}
        if teacher is None:
            ctx['groups'] = Group.objects.filter(is_active=True).order_by('name')
            ctx['today'] = timezone.localdate().isoformat()
        return self.render(request, ctx)


class AttendanceMarkView(UxView):
    template_name = 'new/attendance_mark.html'

    def get(self, request, gid):
        group = group_for(request.user, gid)
        if group is None:
            return redirect('new:attendance')
        now = timezone.localtime()
        date = parse_date(request.GET.get('date'), now.date()) if role_of(request.user) != 'teacher' else now.date()
        session = AttendanceSession.objects.filter(group=group, date=date).first()
        records = {r.student_id: r.status for r in session.records.all()} if session else {}
        saved = bool(records)
        ok, code, msg = check_window(request.user, group, date, now)
        is_admin = role_of(request.user) != 'teacher'
        editable = ok and (is_admin or not saved)
        if not ok:
            reason = msg
        elif saved and not is_admin:
            reason = "Davomat saqlangan. O'zgartirish kerak bo'lsa administratorga yozing."
        else:
            reason = ''
        members = list(group.groupstudent_set.filter(is_active=True, student__is_active=True, joined_at__lte=date)
                       .select_related('student').order_by('student__last_name', 'student__first_name'))
        students = [{'id': m.student_id, 'name': f'{m.student.first_name} {m.student.last_name}',
                     'status': records.get(m.student_id, 'PRESENT')} for m in members]
        plan = LessonPlan.objects.filter(group=group, date=date).first()
        return self.render(request, {
            'group': group, 'date': date, 'students': students, 'editable': editable, 'reason': reason, 'saved': saved,
            'topic': (session.lesson_topic if session and session.lesson_topic else (plan.topic if plan else '')),
            'homework': session.homework if session else '', 'is_admin': is_admin,
            'statuses': AttendanceStatus.choices, 'today': now.date().isoformat(),
        })


@require_POST
@ux_login(json_mode=True)
def api_attendance(request, gid):
    """B6: davomatni saqlash. Mavjud qoidalar: o'qituvchi faqat o'z guruhi, dars vaqtida va bir marta."""
    group = group_for(request.user, gid)
    if group is None:
        return JsonResponse({'detail': "Bu guruh sizga biriktirilmagan."}, status=403)
    data = json_body(request)
    if data is None or not isinstance(data.get('records'), dict):
        return JsonResponse({'detail': "So'rov noto'g'ri."}, status=400)
    now = timezone.localtime()
    is_admin = role_of(request.user) != 'teacher'
    date = parse_date(data.get('date'), now.date()) if is_admin else now.date()
    ok, code, msg = check_window(request.user, group, date, now)
    if not ok:
        return JsonResponse({'detail': msg, 'code': code}, status=403)

    valid = set(AttendanceStatus.values)
    member_ids = set(group.groupstudent_set.filter(is_active=True, student__is_active=True).values_list('student_id', flat=True))
    updates = {}
    for key, status in data['records'].items():
        try:
            sid = int(key)
        except (TypeError, ValueError):
            return JsonResponse({'detail': "O'quvchi ma'lumoti noto'g'ri."}, status=400)
        if sid not in member_ids:
            return JsonResponse({'detail': "Ro'yxatda bu guruhga tegishli bo'lmagan o'quvchi bor. Sahifani yangilang."}, status=400)
        if status not in valid:
            return JsonResponse({'detail': "Davomat holati noto'g'ri."}, status=400)
        updates[sid] = status
    if not updates:
        return JsonResponse({'detail': "Guruhda o'quvchi yo'q."}, status=400)

    with transaction.atomic():
        session, _ = AttendanceSession.objects.select_for_update().get_or_create(
            group=group, date=date, defaults={'teacher': group.teacher or request.user})
        existing = {r.student_id: r.status for r in session.records.all()}
        if existing and not is_admin:
            return JsonResponse({'detail': "Davomat allaqachon saqlangan. O'zgartirish uchun administratorga yozing."}, status=409)
        session.lesson_topic = str(data.get('topic', ''))[:255]
        session.homework = str(data.get('homework', ''))[:2000]
        session.save()
        for sid, status in updates.items():
            AttendanceRecord.objects.update_or_create(session=session, student_id=sid, defaults={'status': status})
        if is_admin:
            AuditLog.objects.create(
                user=request.user, role=request.user.role,
                action="Davomat tuzatildi" if existing else "Administrator davomat kiritdi",
                old_data={'date': str(date), 'group': group.name, 'records': existing} if existing else None,
                new_data={'date': str(date), 'group': group.name, 'records': updates})
    absent = sum(1 for s in updates.values() if s == 'ABSENT')
    return JsonResponse({'ok': True, 'present': sum(1 for s in updates.values() if s in ('PRESENT', 'LATE')), 'absent': absent,
                         'next': reverse('new:attendance')})
