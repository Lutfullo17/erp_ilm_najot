from datetime import timedelta

from django.shortcuts import render, get_object_or_404, redirect
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from users1.views import TeacherRequiredMixin, AdminAccessRequiredMixin
from groups_app.models import Group, GroupStudent
from students.models import Student
from .models import AttendanceSession, AttendanceRecord, AttendanceStatus, LessonPlan
import datetime


class AttendanceMarkView(LoginRequiredMixin, View):
    def test_func(self):
        user = self.request.user
        if user.is_admin_access:
            return True
        if user.is_teacher:
            group = get_object_or_404(Group, id=self.kwargs.get('group_id'))
            return group.teacher == user
        return False

    def get(self, request, group_id):
        group = get_object_or_404(Group, id=group_id)
        today = datetime.date.today()

        now = datetime.datetime.now().time()
        if request.user.is_teacher and not request.user.is_admin_access:
            days_map = {0: 'Dushanba', 1: 'Seshanba', 2: 'Chorshanba', 3: 'Payshanba', 4: 'Juma', 5: 'Shanba', 6: 'Yakshanba'}
            today_name = days_map[today.weekday()]

            lesson_days_list = [d.strip() for d in group.lesson_days.split(',') if d.strip()]

            if not group.lesson_days or today_name not in lesson_days_list:
                messages.error(request, "Bugun ushbu guruh uchun dars kuni emas.")
                return redirect('users1:teacher_groups')
            if not group.lesson_time or not group.end_time:
                messages.error(request, "Guruh dars vaqti to'liq belgilanmagan.")
                return redirect('users1:teacher_groups')
            if now < group.lesson_time:
                messages.error(request, "Dars hali boshlanmagan.")
                return redirect('users1:teacher_groups')
            if now > group.end_time:
                existing_session = AttendanceSession.objects.filter(group=group, date=today).exists()
                if not existing_session:
                    messages.error(request, "Siz ushbu dars uchun davomatni vaqtida olmadingiz. Davomatni tiklash uchun Administrator bilan bog'laning.")
                    return redirect('users1:teacher_groups')

        session, created = AttendanceSession.objects.get_or_create(
            group=group,
            date=today,
            defaults={'teacher': group.teacher}
        )

        if not session.lesson_topic:
            plan = LessonPlan.objects.filter(group=group, date=today).first()
            if plan:
                session.lesson_topic = plan.topic
                session.save()

        records = {r.student_id: r.status for r in session.records.all()}
        students = group.students.filter(groupstudent__is_active=True)

        show_start_alert = False
        is_locked = False

        if request.user.is_teacher and not request.user.is_admin_access:
            if group.lesson_time and now <= group.lesson_time:
                time_diff = datetime.datetime.combine(today, now) - datetime.datetime.combine(today, group.lesson_time)
                if time_diff <= timedelta(minutes=10):
                    show_start_alert = True

            if group.end_time and now > group.end_time:
                is_locked = True

        return render(request, 'attendance/mark_attendance.html', {
            'group': group,
            'session': session,
            'students': students,
            'records': records,
            'status_choices': AttendanceStatus.choices,
            'show_start_alert': show_start_alert,
            'is_locked': is_locked,
            'lesson_start': group.lesson_time,
            'lesson_end': group.end_time,
        })

    def post(self, request, group_id):
        group = get_object_or_404(Group, id=group_id)
        today = datetime.date.today()
        now = datetime.datetime.now().time()

        if request.user.is_teacher and not request.user.is_admin_access:
            days_map = {0: 'Dushanba', 1: 'Seshanba', 2: 'Chorshanba', 3: 'Payshanba', 4: 'Juma', 5: 'Shanba', 6: 'Yakshanba'}
            today_name = days_map[today.weekday()]

            lesson_days_list = [d.strip() for d in group.lesson_days.split(',') if d.strip()]

            if not group.lesson_days or today_name not in lesson_days_list:
                messages.error(request, "Bugun ushbu guruh uchun dars kuni emas.")
                return redirect('users1:teacher_groups')
            if not group.lesson_time or not group.end_time:
                messages.error(request, "Guruh dars vaqti to'liq belgilanmagan.")
                return redirect('users1:teacher_groups')
            if now < group.lesson_time:
                messages.error(request, "Dars hali boshlanmagan.")
                return redirect('users1:teacher_groups')
            if now > group.end_time:
                messages.error(request, "Siz ushbu dars uchun davomatni vaqtida olmadingiz. Davomatni tiklash uchun Administrator bilan bog'laning.")
                return redirect('users1:teacher_groups')

        if request.user.is_admin_access:
            from reports.models import AuditLog
            AuditLog.objects.create(
                user=request.user, role=request.user.role,
                action="Administrator tomonidan davomat qo'lda kiritildi",
                new_data={'group_id': group.id, 'group_name': group.name, 'date': str(today)}
            )

        session, created = AttendanceSession.objects.get_or_create(
            group=group,
            date=today,
            defaults={'teacher': group.teacher}
        )

        session.lesson_topic = request.POST.get('lesson_topic', '')
        session.homework = request.POST.get('homework', '')
        session.save()

        for key, value in request.POST.items():
            if key.startswith('status_'):
                student_id = key.split('_')[1]
                AttendanceRecord.objects.update_or_create(
                    session=session,
                    student_id=student_id,
                    defaults={'status': value}
                )

        if request.user.is_teacher:
            return redirect('users1:teacher_dashboard')
        return redirect('groups_app:group_detail', pk=group_id)


@require_http_methods(['POST'])
def admin_override_attendance(request, group_id):
    """Admin/Director tomonidan davomatni vaqtidan tashqari kiritish."""
    user = request.user
    if not user.is_authenticated or not user.is_admin_access:
        return JsonResponse({'detail': "Faqat Admin/Director uchun ruxsat bor."}, status=403)

    group = get_object_or_404(Group, pk=group_id, is_active=True)

    import json
    try:
        payload = json.loads(request.body.decode('utf-8'))
    except Exception:
        return JsonResponse({'detail': "Noto'g'ri ma'lumot"}, status=400)

    date_str = payload.get('date')
    if not date_str:
        return JsonResponse({'detail': "Sana talab qilinadi."}, status=400)

    try:
        override_date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return JsonResponse({'detail': "Noto'g'ri sana formati."}, status=400)

    session, created = AttendanceSession.objects.get_or_create(
        group=group,
        date=override_date,
        defaults={'teacher': group.teacher}
    )

    from reports.models import AuditLog
    AuditLog.objects.create(
        user=user,
        role=user.role,
        action="Admin Override: Davomat vaqtidan tashqari kiritildi",
        new_data={
            'group_id': group.id,
            'group_name': group.name,
            'date': str(override_date),
        }
    )

    return JsonResponse({
        'ok': True,
        'session_id': session.id,
        'created': created,
        'message': f"Davomat {override_date.strftime('%d.%m.%Y')} uchun muvaffaqiyatli ochildi.",
    })


@require_http_methods(['POST'])
def save_lesson_plan(request):
    import json
    try:
        payload = json.loads(request.body.decode('utf-8'))
    except Exception:
        return JsonResponse({'detail': "Noto'g'ri ma'lumot"}, status=400)

    group_id = payload.get('group_id')
    date_str = payload.get('date')
    topic = payload.get('topic', '').strip()

    if not group_id or not date_str:
        return JsonResponse({'detail': 'Guruh va sana talab qilinadi'}, status=400)

    group = Group.objects.filter(pk=group_id, is_active=True).first()
    if not group:
        return JsonResponse({'detail': 'Guruh topilmadi'}, status=404)

    try:
        plan_date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return JsonResponse({'detail': "Noto'g'ri sana formati"}, status=400)

    plan, created = LessonPlan.objects.update_or_create(
        group=group,
        date=plan_date,
        defaults={
            'teacher': request.user,
            'topic': topic,
        }
    )

    return JsonResponse({'ok': True, 'created': created})
