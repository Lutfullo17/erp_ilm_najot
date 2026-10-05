import datetime

from django.contrib import messages
from django.db.models import Avg, Count, Q
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

from attendance.models import AttendanceRecord
from bot.models import TelegramAppeal, TelegramUser
from grades.models import GradeSession
from grades.services import GradeInputError, get_grade_snapshot
from groups_app.models import Group, GroupStudent, Room
from students.models import Student
from users1.models import ScheduleChangeRequest
from users1.views import ScheduleChangeRequestForm, TeacherScheduleView, review_schedule_change_request, _compute_end_time
from django.core.exceptions import PermissionDenied

from . import services
from .base import UxView, ux_login
from .views_reports import _context_of

ADMIN = {'administrator', 'director'}
TEACHER = {'teacher'}


class ScheduleView(UxView):
    roles = ADMIN
    template_name = 'new/schedule.html'

    def get(self, request):
        today = timezone.localdate()
        day = request.GET.get('day')
        if day not in services.DAY_NAMES:
            day = services.DAY_NAMES[today.weekday()]
        groups = Group.objects.filter(is_active=True, lesson_time__isnull=False).select_related('teacher').order_by('lesson_time')
        rooms = []
        for val, label in Room.choices:
            lessons = [g for g in groups if g.room == val and day in {d.strip() for d in (g.lesson_days or '').split(',')}]
            rooms.append({'id': val, 'label': label, 'lessons': lessons})
        no_room = [g for g in groups if not g.room and day in {d.strip() for d in (g.lesson_days or '').split(',')}]
        pending = ScheduleChangeRequest.objects.filter(status=ScheduleChangeRequest.Status.PENDING).select_related('teacher', 'group').order_by('submitted_at')
        show_all = request.GET.get('all') == '1'
        done_qs = ScheduleChangeRequest.objects.exclude(status=ScheduleChangeRequest.Status.PENDING).select_related('teacher', 'group', 'reviewed_by').order_by('-submitted_at')
        done_total = done_qs.count()
        done = done_qs[:200] if show_all else done_qs[:10]
        return self.render(request, {'day': day, 'show_all': show_all, 'done_total': done_total, 'days': services.DAY_NAMES, 'rooms': rooms, 'no_room': no_room, 'pending': pending, 'done': done,
                                     'room_choices': Room.choices})


@require_POST
@ux_login(ADMIN)
def schedule_review(request, pk):
    """Eski `review_schedule_change_request` mantig'ini chaqiradi (to'qnashuv tekshiruvi, bildirishnoma, audit)."""
    try:
        review_schedule_change_request(request, pk)
    except PermissionDenied:
        messages.error(request, "Ruxsat yo'q.")
    return redirect('new:schedule')


class MyScheduleView(UxView):
    roles = TEACHER
    template_name = 'new/my_schedule.html'

    def get(self, request):
        ctx = _context_of(TeacherScheduleView, request)
        ctx['requests'] = ScheduleChangeRequest.objects.filter(teacher=request.user).select_related('group', 'reviewed_by').order_by('-submitted_at')[:10]
        return self.render(request, ctx)


class RequestNewView(UxView):
    roles = TEACHER
    template_name = 'new/request_form.html'

    def _setup(self, request, gid):
        group = get_object_or_404(Group, pk=gid, teacher=request.user, is_active=True)
        days = [d.strip() for d in (group.lesson_days or '').split(',') if d.strip()]
        old_day = request.GET.get('day')
        if old_day not in days:
            old_day = days[0] if days else None
        return group, days, old_day

    def get(self, request, gid):
        group, days, old_day = self._setup(request, gid)
        if not old_day:
            messages.error(request, "Guruhning dars kuni belgilanmagan.")
            return redirect('new:my_schedule')
        form = ScheduleChangeRequestForm(group=group, teacher=request.user, old_day=old_day,
                                         old_start_time=group.lesson_time, old_end_time=_compute_end_time(group))
        return self.render(request, {'group': group, 'form': form, 'old_day': old_day, 'rooms': Room.choices, 'days': services.DAY_NAMES})

    def post(self, request, gid):
        group, days, old_day = self._setup(request, gid)
        if not old_day:
            return redirect('new:my_schedule')
        form = ScheduleChangeRequestForm(request.POST, group=group, teacher=request.user, old_day=old_day,
                                         old_start_time=group.lesson_time, old_end_time=_compute_end_time(group))
        if form.is_valid():
            req = form.save()
            from users1.views import create_audit_log
            create_audit_log(request, f"Jadval o'zgartirish arizasi yaratildi: {group.name} ({old_day} {group.lesson_time} -> {req.new_day} {req.new_start_time})", target_user=request.user)
            messages.success(request, "So'rovingiz yuborildi. Administrator ko'rib chiqadi.")
            return redirect('new:my_schedule')
        return self.render(request, {'group': group, 'form': form, 'old_day': old_day, 'rooms': Room.choices, 'days': services.DAY_NAMES}, status=400)


# ----------------------------------------------------------------------- O'qituvchi: guruhlar va baholar

class MyStudentsView(UxView):
    roles = TEACHER
    template_name = 'new/my_students.html'

    def get(self, request):
        from users1.views import TeacherStudentsView
        ctx = _context_of(TeacherStudentsView, request)
        rows = sorted(ctx['students_data'], key=lambda r: (r['student'].last_name or '', r['student'].first_name or ''))
        return self.render(request, {'rows': rows})


class MyGroupsView(UxView):
    roles = TEACHER
    template_name = 'new/my_groups.html'

    def get(self, request):
        groups = Group.objects.filter(teacher=request.user, is_active=True).annotate(
            n=Count('groupstudent', filter=Q(groupstudent__is_active=True, groupstudent__student__is_active=True))).order_by('name')
        return self.render(request, {'groups': groups})


class MyGroupView(UxView):
    roles = TEACHER
    template_name = 'new/my_group.html'

    def get(self, request, pk):
        group = get_object_or_404(Group, pk=pk, teacher=request.user, is_active=True)
        members = list(GroupStudent.objects.filter(group=group, is_active=True, student__is_active=True).select_related('student')
                       .order_by('student__last_name', 'student__first_name'))
        last = {}
        for r in AttendanceRecord.objects.filter(session__group=group, student_id__in=[m.student_id for m in members]).select_related('session').order_by('session__date'):
            last[r.student_id] = r
        for m in members:
            m.last = last.get(m.student_id)
        return self.render(request, {'group': group, 'members': members})


class MyStudentView(UxView):
    roles = TEACHER
    template_name = 'new/my_student.html'

    def get(self, request, pk):
        student = get_object_or_404(Student, pk=pk, is_active=True)
        if not GroupStudent.objects.filter(group__teacher=request.user, group__is_active=True, student=student, is_active=True).exists():
            messages.error(request, "Bu o'quvchi sizning guruhlaringizda emas.")
            return redirect('new:my_groups')
        groups = Group.objects.filter(groupstudent__student=student, groupstudent__is_active=True, is_active=True)
        att = AttendanceRecord.objects.filter(student=student, session__teacher=request.user).select_related('session__group').order_by('-session__date')[:10]
        return self.render(request, {
            'student': student, 'groups': groups, 'attendance': att,
            'telegram': TelegramUser.objects.filter(student=student, is_verified=True).first(),
            'appeals': TelegramAppeal.objects.filter(student=student).order_by('-created_at')[:5],
        })


class GradesView(UxView):
    roles = TEACHER
    template_name = 'new/grades.html'

    def get(self, request):
        today = timezone.localdate()
        groups = list(Group.objects.filter(teacher=request.user, is_active=True).order_by('name'))
        gid = request.GET.get('group') or (str(groups[0].pk) if len(groups) == 1 else '')
        date = request.GET.get('date') or today.isoformat()
        title = (request.GET.get('title') or 'Dars bahosi').strip()[:150]
        snapshot, error = None, ''
        if gid:
            try:
                snapshot = get_grade_snapshot(request.user, gid, date, title)
            except GradeInputError as exc:
                error = str(exc)
            except Exception:
                error = "Baholash uchun ma'lumot topilmadi."
        history = GradeSession.objects.filter(teacher=request.user).select_related('group').annotate(
            n=Count('records'), avg=Avg('records__percentage')).order_by('-date')[:15]
        return self.render(request, {'groups': groups, 'gid': gid, 'date': date, 'title': title, 'snapshot': snapshot, 'error': error,
                                     'history': history, 'today': today.isoformat()})
