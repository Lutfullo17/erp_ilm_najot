from django.shortcuts import render, get_object_or_404, redirect
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from users1.views import TeacherRequiredMixin, AdminRequiredMixin
from groups_app.models import Group
from .models import AttendanceSession, AttendanceRecord, AttendanceStatus
import datetime

class AttendanceMarkView(LoginRequiredMixin, View):
    def get(self, request, group_id):
        group = get_object_or_404(Group, id=group_id)
        today = datetime.date.today()
        session, created = AttendanceSession.objects.get_or_create(
            group=group, 
            date=today,
            defaults={'teacher': group.teacher}
        )
        
        # Get existing records
        records = {r.student_id: r.status for r in session.records.all()}
        
        students = group.students.filter(groupstudent__is_active=True)
        
        return render(request, 'attendance/mark_attendance.html', {
            'group': group,
            'session': session,
            'students': students,
            'records': records,
            'status_choices': AttendanceStatus.choices
        })

    def post(self, request, group_id):
        group = get_object_or_404(Group, id=group_id)
        session = get_object_or_404(AttendanceSession, group=group, date=datetime.date.today())
        
        from bot.notifications import send_attendance_notification
        
        for key, value in request.POST.items():
            if key.startswith('status_'):
                student_id = key.split('_')[1]
                record, created = AttendanceRecord.objects.update_or_create(
                    session=session,
                    student_id=student_id,
                    defaults={'status': value}
                )
                # Send notification only if status is ABSENT
                if value == 'ABSENT':
                    send_attendance_notification(record.student, group, session.date)
        
        return redirect('groups_app:group_detail', pk=group_id)
