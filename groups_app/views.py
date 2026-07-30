from django.http import JsonResponse
from django.contrib import messages
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.decorators.http import require_http_methods
from django.views.generic import ListView, CreateView, UpdateView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from users1.views import AdminAccessRequiredMixin
from .models import Group, GroupStudent, Room
from students.models import Student
from users1.models import ScheduleChangeRequest, AuditLog
import datetime


class RoomAvailabilityView(LoginRequiredMixin, AdminAccessRequiredMixin, ListView):
    template_name = 'groups_app/room_availability.html'
    context_object_name = 'rooms_data'

    def get_queryset(self):
        rooms = Room.choices
        days_of_week = ['Dushanba', 'Seshanba', 'Chorshanba', 'Payshanba', 'Juma', 'Shanba', 'Yakshanba']
        today = timezone.localdate()
        today_name = days_of_week[today.weekday()]
        now_time = timezone.localtime().time()

        schedule = []
        active_groups = Group.objects.filter(is_active=True).select_related('teacher')

        for r_val, r_label in rooms:
            room_days = []
            for day in days_of_week:
                day_groups = []
                for g in active_groups:
                    if g.room == r_val and g.lesson_days and day in g.lesson_days:
                        # O'tgan darslarni belgilash
                        is_past = False
                        if day == today_name and g.lesson_time:
                            # Dars tugaganmi?
                            if g.end_time:
                                is_past = now_time > g.end_time
                            elif g.duration:
                                hours = int(g.duration)
                                minutes = int((g.duration - hours) * 60)
                                end = (datetime.datetime.combine(today, g.lesson_time) + datetime.timedelta(hours=hours, minutes=minutes)).time()
                                is_past = now_time > end
                            # Agar kun o'tgan bo'lsa
                        elif days_of_week.index(day) < days_of_week.index(today_name):
                            is_past = True
                        elif days_of_week.index(day) > days_of_week.index(today_name):
                            is_past = False
                        # Shu kun, lekin hali dars boshlanmagan yoki davom etayotgan
                        elif day == today_name:
                            is_past = False

                        day_groups.append({
                            'pk': g.pk,
                            'name': g.name,
                            'lesson_time': g.lesson_time,
                            'teacher': g.teacher,
                            'room': g.room,
                            'is_past': is_past,
                        })

                day_groups.sort(key=lambda x: x['lesson_time'] if x['lesson_time'] else datetime.time(0, 0))
                room_days.append({
                    'day': day,
                    'groups': day_groups
                })

            schedule.append({
                'id': r_val,
                'name': r_label,
                'days': room_days
            })

        return schedule

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        days_of_week = ['Dushanba', 'Seshanba', 'Chorshanba', 'Payshanba', 'Juma', 'Shanba', 'Yakshanba']
        today = timezone.localdate()
        context['days'] = days_of_week
        context['today_name'] = days_of_week[today.weekday()]
        context['rooms'] = Room.choices
        from users1.models import User
        context['teachers'] = User.objects.filter(role='TEACHER', is_active=True, is_deleted=False).order_by('last_name', 'first_name')
        return context


class GroupListView(LoginRequiredMixin, AdminAccessRequiredMixin, ListView):
    model = Group
    template_name = 'groups_app/group_list.html'
    context_object_name = 'groups'

    def get_queryset(self):
        query = self.request.GET.get('q')
        if query:
            return Group.objects.filter(name__icontains=query)
        return Group.objects.all()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_count'] = Group.objects.filter(is_active=True, is_paused=False).count()
        context['paused_count'] = Group.objects.filter(is_paused=True).count()
        context['total_students_count'] = GroupStudent.objects.filter(is_active=True, group__is_active=True).count()
        return context


class GroupDetailView(LoginRequiredMixin, AdminAccessRequiredMixin, DetailView):
    model = Group
    template_name = 'groups_app/group_detail.html'
    context_object_name = 'group'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['group_students'] = self.object.groupstudent_set.filter(is_active=True).select_related('student')
        context['all_students'] = Student.objects.filter(is_active=True).exclude(id__in=self.object.students.all())
        return context


class GroupCreateView(LoginRequiredMixin, AdminAccessRequiredMixin, CreateView):
    model = Group
    template_name = 'groups_app/group_form.html'
    fields = ['name', 'monthly_fee', 'teacher', 'start_date', 'lesson_days', 'lesson_time', 'duration', 'room']
    success_url = reverse_lazy('groups_app:group_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['rooms'] = Group._meta.get_field('room').choices
        return context

    def form_valid(self, form):
        from django.core.exceptions import ValidationError as DjangoValidationError
        obj = form.save(commit=False)
        try:
            obj.full_clean()
        except DjangoValidationError as e:
            for field, msgs in e.message_dict.items():
                if field in form.fields:
                    form.add_error(field, msgs)
                else:
                    form.add_error(None, msgs)
            return self.form_invalid(form)
        obj.save()
        from users1.models import AuditLog
        new_data = {'teacher': obj.teacher_id, 'room': obj.room, 'lesson_time': str(obj.lesson_time) if obj.lesson_time else None, 'duration': str(obj.duration) if obj.duration else None}
        AuditLog.objects.create(
            user=self.request.user, role=self.request.user.role,
            action="Guruh yaratildi", new_data=new_data
        )
        messages.success(self.request, f"'{obj.name}' guruhi muvaffaqiyatli yaratildi.")
        return redirect(self.success_url)


class GroupUpdateView(LoginRequiredMixin, AdminAccessRequiredMixin, UpdateView):
    model = Group
    template_name = 'groups_app/group_form.html'
    fields = ['name', 'monthly_fee', 'teacher', 'start_date', 'lesson_days', 'lesson_time', 'duration', 'room']
    success_url = reverse_lazy('groups_app:group_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['rooms'] = Group._meta.get_field('room').choices
        return context

    def form_valid(self, form):
        from django.core.exceptions import ValidationError as DjangoValidationError
        obj = form.save(commit=False)
        try:
            obj.full_clean()
        except DjangoValidationError as e:
            for field, msgs in e.message_dict.items():
                if field in form.fields:
                    form.add_error(field, msgs)
                else:
                    form.add_error(None, msgs)
            return self.form_invalid(form)
        old_obj = Group.objects.get(pk=obj.pk) if obj.pk else None
        old_data = {'teacher': old_obj.teacher_id, 'room': old_obj.room, 'lesson_time': str(old_obj.lesson_time) if old_obj.lesson_time else None, 'duration': str(old_obj.duration) if old_obj.duration else None} if old_obj else None
        obj.save()
        from users1.models import AuditLog
        new_data = {'teacher': obj.teacher_id, 'room': obj.room, 'lesson_time': str(obj.lesson_time) if obj.lesson_time else None, 'duration': str(obj.duration) if obj.duration else None}
        AuditLog.objects.create(
            user=self.request.user, role=self.request.user.role,
            action="Guruh tahrirlandi", old_data=old_data, new_data=new_data
        )
        messages.success(self.request, f"'{obj.name}' guruhi muvaffaqiyatli yangilandi.")
        return redirect(self.success_url)


def add_student_to_group(request, pk):
    if not request.user.is_authenticated or not request.user.is_admin_access:
        messages.error(request, "Ruxsat yo'q.")
        return redirect('users1:login')
    group = get_object_or_404(Group, pk=pk)
    if request.method == 'POST':
        student_id = request.POST.get('student_id')
        if student_id:
            student = get_object_or_404(Student, pk=student_id)
            gs, created = GroupStudent.objects.get_or_create(group=group, student=student)
            if not gs.is_active:
                gs.is_active = True
                gs.save()
    return redirect('groups_app:group_detail', pk=pk)


@login_required
@require_http_methods(['GET', 'POST'])
def add_student_to_group_modal(request, student_pk):
    if not request.user.is_admin_access:
        messages.error(request, "Ruxsat yo'q.")
        return redirect('users1:login')
    
    student = get_object_or_404(Student, pk=student_pk)
    
    if request.method == 'POST':
        group_id = request.POST.get('group_id')
        if group_id:
            group = get_object_or_404(Group, pk=group_id)
            gs, created = GroupStudent.objects.get_or_create(group=group, student=student)
            if not gs.is_active:
                gs.is_active = True
                gs.save()
            if created:
                messages.success(request, f"{student.get_full_name()} {group.name} guruhiga qo'shildi.")
            else:
                messages.info(request, f"{student.get_full_name()} allaqachon {group.name} guruhida.")
            return redirect('students:student_detail', pk=student_pk)
    
    # Get groups that the student is NOT already a member of
    existing_group_ids = student.groups.filter(groupstudent__is_active=True).values_list('id', flat=True)
    available_groups = Group.objects.exclude(id__in=existing_group_ids).filter(is_active=True)
    
    return render(request, 'groups_app/add_student_to_group_modal.html', {
        'student': student,
        'available_groups': available_groups,
    })


@require_http_methods(['POST'])
def delete_group(request, pk):
    if not request.user.is_authenticated or not request.user.is_director:
        messages.error(request, "Faqat Director guruhlarni o'chira oladi.")
        return redirect('groups_app:group_list')
    from django.db.models import ProtectedError
    group = get_object_or_404(Group, pk=pk)
    try:
        group.delete()
        messages.success(request, f"'{group.name}' guruhi butunlay o'chirildi.")
    except ProtectedError:
        # Agar guruhda darslar yoki baholar bo'lsa, o'chirib bo'lmaydi
        messages.error(
            request, 
            f"'{group.name}' guruhini o'chirib bo'lmaydi, chunki unda davomat yoki baholash ma'lumotlari mavjud. "
            "Uni arxivlash (statusini faol emas qilish) tavsiya etiladi."
        )
    return redirect('groups_app:group_list')


@require_http_methods(['POST'])
def toggle_pause_group(request, pk):
    if not request.user.is_authenticated or not request.user.is_admin_access:
        messages.error(request, "Ruxsat yo'q.")
        return redirect('groups_app:group_list')
    group = get_object_or_404(Group, pk=pk)
    group.is_paused = not group.is_paused
    group.save()
    status = "to'xtatildi" if group.is_paused else "faollashtirildi"
    messages.success(request, f"'{group.name}' guruh vaqtincha {status}.")
    return redirect('groups_app:group_detail', pk=pk)


DAY_ORDER = {
    'Dushanba': 0, 'Seshanba': 1, 'Chorshanba': 2,
    'Payshanba': 3, 'Juma': 4, 'Shanba': 5, 'Yakshanba': 6,
}


@login_required
def admin_edit_lesson_page(request, group_pk, target_day):
    """Dars tahrirlash sahifasi (GET) — alohida sahifa sifatida."""
    if not request.user.is_admin_access:
        messages.error(request, "Ruxsat yo'q.")
        return redirect('groups_app:room_availability')

    group = get_object_or_404(Group, pk=group_pk, is_active=True)

    if target_day not in DAY_ORDER:
        messages.error(request, "Noto'g'ri kun.")
        return redirect('groups_app:room_availability')

    current_time = group.lesson_time.strftime('%H:%M') if group.lesson_time else ''
    current_room = str(group.room) if group.room else ''
    group_name = group.name
    teacher_name = group.teacher.get_full_name() if group.teacher else ''

    context = {
        'group': group,
        'target_day': target_day,
        'current_time': current_time,
        'current_room': current_room,
        'group_name': group_name,
        'teacher_name': teacher_name,
        'rooms': Room.choices,
    }
    return render(request, 'groups_app/admin_edit_lesson.html', context)


@require_http_methods(['POST'])
def admin_edit_lesson(request, group_pk, target_day):
    """
    Admin/Administrator tomonidan darsni to'g'ridan-to'g'ri tahrirlash (1 kun uchun).
    Xona, vaqt va kun o'zgartirilishi mumkin.
    """
    if not request.user.is_authenticated or not request.user.is_admin_access:
        return JsonResponse({'error': "Ruxsat yo'q"}, status=403)

    group = get_object_or_404(Group, pk=group_pk, is_active=True)

    if target_day not in DAY_ORDER:
        return JsonResponse({'error': "Noto'g'ri kun"}, status=400)

    try:
        import json as json_module
        data = json_module.loads(request.body)
    except Exception:
        return JsonResponse({'error': "Noto'g'ri ma'lumot"}, status=400)

    new_day = data.get('new_day', '').strip()
    new_room = data.get('room')
    new_start_time_str = data.get('start_time', '').strip()
    reason = data.get('reason', '').strip()

    # Sabab majburiy
    if not reason:
        return JsonResponse({'error': "Sababni kiriting"}, status=400)

    # Yangi kun validatsiyasi
    if new_day and new_day not in DAY_ORDER:
        return JsonResponse({'error': "Noto'g'ri kun tanlandi"}, status=400)

    # Validatsiya: kamida bitta o'zgarish kerak
    if not new_day and not new_room and not new_start_time_str:
        return JsonResponse({'error': "Kamida bitta o'zgarish tanlang"}, status=400)

    # Eski qiymatlarni saqlash (audit log uchun)
    old_room = group.room
    old_lesson_time = group.lesson_time
    old_day = target_day

    # Yangi kun (agar o'zgartirilgan bo'lsa)
    final_new_day = new_day if new_day else target_day

    # Xona validatsiyasi
    if new_room is not None:
        try:
            new_room = int(new_room)
        except (TypeError, ValueError):
            return JsonResponse({'error': "Noto'g'ri xona raqami"}, status=400)
        valid_rooms = [r[0] for r in Room.choices]
        if new_room not in valid_rooms:
            return JsonResponse({'error': "Noto'g'ri xona"}, status=400)
    else:
        new_room = group.room

    # Vaqt validatsiyasi
    new_start_time = group.lesson_time
    if new_start_time_str:
        try:
            new_start_time = datetime.time.fromisoformat(new_start_time_str)
        except (ValueError, TypeError):
            return JsonResponse({'error': "Noto'g'ri vaqt formati. Namuna: 14:00"}, status=400)

    # Tugash vaqtini hisoblash
    if group.duration:
        hours = int(group.duration)
        minutes = int((group.duration - hours) * 60)
        new_end_time = (datetime.datetime.combine(datetime.date.today(), new_start_time) + datetime.timedelta(hours=hours, minutes=minutes)).time()
    elif group.end_time:
        duration_hours = (datetime.datetime.combine(datetime.date.today(), group.end_time) - datetime.datetime.combine(datetime.date.today(), group.lesson_time)).seconds / 3600
        h = int(duration_hours)
        m = int((duration_hours - h) * 60)
        new_end_time = (datetime.datetime.combine(datetime.date.today(), new_start_time) + datetime.timedelta(hours=h, minutes=m)).time()
    else:
        return JsonResponse({'error': "Guruh davomiyligi aniqlanmagan"}, status=400)

    # Validatsiya: konfliktlar (yangi kun uchun)
    from users1.services import validate_schedule_change
    errors = validate_schedule_change(
        group=group,
        new_day=final_new_day,
        new_start_time=new_start_time,
        new_end_time=new_end_time,
        new_room=new_room,
    )

    if errors:
        return JsonResponse({'error': ' | '.join(errors)}, status=400)

    # ScheduleChangeRequest yaratish
    today = timezone.localdate()
    schedule_request = ScheduleChangeRequest.objects.create(
        teacher=group.teacher,
        group=group,
        old_day=old_day,
        old_start_time=old_lesson_time,
        old_end_time=group.end_time,
        new_day=final_new_day,
        new_start_time=new_start_time,
        new_end_time=new_end_time,
        reason=reason,
        status=ScheduleChangeRequest.Status.APPROVED,
        effective_week_start=_start_of_week(today),
        change_date=today,
        change_type=ScheduleChangeRequest.ChangeType.ADMIN_DIRECT,
        reviewed_by=request.user,
        reviewed_at=timezone.now(),
        review_comment="Admin tomonidan to'g'ridan-to'g'ri o'zgartirildi",
    )

    # Guruhni yangilash — kun o'zgargan bo'lsa lesson_days ni ham yangilash
    group.lesson_time = new_start_time
    group.end_time = new_end_time
    group.room = new_room

    if new_day and new_day != target_day:
        # Kunlarni yangilash: eski kuni o'chirib, yangisini qo'shish
        current_days = [d.strip() for d in group.lesson_days.split(',') if d.strip()]
        if target_day in current_days:
            current_days.remove(target_day)
        if new_day not in current_days:
            current_days.append(new_day)
        group.lesson_days = ', '.join(current_days)

    group.save()

    # Audit log
    AuditLog.objects.create(
        user=request.user,
        target_user=group.teacher,
        action=f"Dars tahrirlandi (admin): {group.name} - {old_day} → {final_new_day}, {new_start_time.strftime('%H:%M')}",
        old_data={
            'room': old_room,
            'lesson_time': str(old_lesson_time.strftime('%H:%M')) if old_lesson_time else None,
            'day': old_day,
        },
        new_data={
            'room': new_room,
            'lesson_time': new_start_time.strftime('%H:%M'),
            'day': final_new_day,
        },
        ip_address=request.META.get('REMOTE_ADDR'),
    )

    # Xabarnomalar yuborish
    from users1.services import send_schedule_change_notifications
    send_schedule_change_notifications(schedule_request)

    return JsonResponse({
        'ok': True,
        'message': f"Dars muvaffaqiyatli o'zgartirildi: {final_new_day} {new_start_time.strftime('%H:%M')}",
    })


def _start_of_week(value):
    return value - timezone.timedelta(days=value.weekday())
