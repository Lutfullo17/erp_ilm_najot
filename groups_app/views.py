from django.http import JsonResponse
from django.contrib import messages
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.decorators.http import require_http_methods
from django.views.generic import ListView, CreateView, UpdateView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin
from users1.views import AdminAccessRequiredMixin
from .models import Group, GroupStudent, Room
from students.models import Student
import datetime


class RoomAvailabilityView(LoginRequiredMixin, AdminAccessRequiredMixin, ListView):
    template_name = 'groups_app/room_availability.html'
    context_object_name = 'rooms_data'

    def get_queryset(self):
        # We'll build a data structure: {room_id: {day: [groups]}}
        rooms = Room.choices
        days_of_week = ['Dushanba', 'Seshanba', 'Chorshanba', 'Payshanba', 'Juma', 'Shanba', 'Yakshanba']
        
        schedule = []
        active_groups = Group.objects.filter(is_active=True).select_related('teacher')
        
        for r_val, r_label in rooms:
            room_days = []
            for day in days_of_week:
                day_groups = [
                    g for g in active_groups 
                    if g.room == r_val and g.lesson_days and day in g.lesson_days
                ]
                # Sort by time
                day_groups.sort(key=lambda x: x.lesson_time if x.lesson_time else datetime.time(0,0))
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
        context['days'] = ['Dushanba', 'Seshanba', 'Chorshanba', 'Payshanba', 'Juma', 'Shanba', 'Yakshanba']
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

