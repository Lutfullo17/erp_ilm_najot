from django.http import JsonResponse
from django.contrib import messages
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.decorators.http import require_http_methods
from django.views.generic import ListView, CreateView, UpdateView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin
from users1.views import AdminRequiredMixin
from .models import Group, GroupStudent
from students.models import Student


class GroupListView(LoginRequiredMixin, AdminRequiredMixin, ListView):
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


class GroupDetailView(LoginRequiredMixin, AdminRequiredMixin, DetailView):
    model = Group
    template_name = 'groups_app/group_detail.html'
    context_object_name = 'group'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['group_students'] = self.object.groupstudent_set.filter(is_active=True).select_related('student')
        context['all_students'] = Student.objects.filter(is_active=True).exclude(id__in=self.object.students.all())
        return context


class GroupCreateView(LoginRequiredMixin, AdminRequiredMixin, CreateView):
    model = Group
    template_name = 'groups_app/group_form.html'
    fields = ['name', 'monthly_fee', 'teacher', 'start_date', 'lesson_days', 'lesson_time', 'room']
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
        messages.success(self.request, f"'{obj.name}' guruhi muvaffaqiyatli yaratildi.")
        return redirect(self.success_url)


class GroupUpdateView(LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    model = Group
    template_name = 'groups_app/group_form.html'
    fields = ['name', 'monthly_fee', 'teacher', 'start_date', 'lesson_days', 'lesson_time', 'room']
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
        messages.success(self.request, f"'{obj.name}' guruhi muvaffaqiyatli yangilandi.")
        return redirect(self.success_url)


def add_student_to_group(request, pk):
    group = get_object_or_404(Group, pk=pk)
    if request.method == 'POST':
        student_id = request.POST.get('student_id')
        if student_id:
            student = get_object_or_404(Student, pk=student_id)
            GroupStudent.objects.get_or_create(group=group, student=student, defaults={'is_active': True})
    return redirect('groups_app:group_detail', pk=pk)


@require_http_methods(['POST'])
def delete_group(request, pk):
    group = get_object_or_404(Group, pk=pk)
    group.delete()
    messages.success(request, f"'{group.name}' guruh o'chirildi.")
    return redirect('groups_app:group_list')


@require_http_methods(['POST'])
def toggle_pause_group(request, pk):
    group = get_object_or_404(Group, pk=pk)
    group.is_paused = not group.is_paused
    group.save()
    status = "to'xtatildi" if group.is_paused else "faollashtirildi"
    messages.success(request, f"'{group.name}' guruh vaqtincha {status}.")
    return redirect('groups_app:group_detail', pk=pk)

