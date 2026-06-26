from django import forms
from django.contrib import messages
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin
from users1.views import AdminRequiredMixin
from groups_app.models import Group, GroupStudent
from .models import Student


class StudentQuickForm(forms.ModelForm):
    class Meta:
        model = Student
        fields = ['phone', 'parent_phone']


class StudentListView(LoginRequiredMixin, AdminRequiredMixin, ListView):
    model = Student
    template_name = 'students/student_list.html'
    context_object_name = 'students'
    paginate_by = 15

    def get_queryset(self):
        query = self.request.GET.get('q')
        if query:
            return Student.objects.filter(
                first_name__icontains=query
            ) | Student.objects.filter(
                last_name__icontains=query
            ) | Student.objects.filter(
                phone__icontains=query
            )
        return Student.objects.all()


class StudentDetailView(LoginRequiredMixin, AdminRequiredMixin, DetailView):
    model = Student
    template_name = 'students/student_detail.html'
    context_object_name = 'student'


class StudentCreateView(LoginRequiredMixin, AdminRequiredMixin, CreateView):
    model = Student
    form_class = StudentQuickForm
    template_name = 'students/student_form.html'
    success_url = reverse_lazy('students:student_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['groups'] = Group.objects.filter(is_active=True).order_by('name')
        return context

    def form_valid(self, form):
        full_name = self.request.POST.get('full_name', '').strip()
        if not full_name:
            form.add_error(None, "Ism-familiyani kiriting.")
            return self.form_invalid(form)

        parts = full_name.split(None, 1)
        form.instance.first_name = parts[0]
        form.instance.last_name = parts[1] if len(parts) > 1 else ''

        student = form.save()
        group_id = self.request.POST.get('group')
        if group_id:
            group = Group.objects.filter(pk=group_id, is_active=True).first()
            if group:
                GroupStudent.objects.get_or_create(
                    group=group, student=student,
                    defaults={'is_active': True},
                )
        messages.success(self.request, "O'quvchi muvaffaqiyatli qo'shildi!")
        return redirect(self.success_url)


class StudentUpdateView(LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    model = Student
    form_class = StudentQuickForm
    template_name = 'students/student_form.html'
    success_url = reverse_lazy('students:student_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['groups'] = Group.objects.filter(is_active=True).order_by('name')
        return context
