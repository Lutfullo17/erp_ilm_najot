from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin
from users1.views import AdminRequiredMixin
from .models import Student

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
    template_name = 'students/student_form.html'
    fields = ['first_name', 'last_name', 'phone', 'birth_date', 'address', 'is_active']
    success_url = reverse_lazy('students:student_list')

class StudentUpdateView(LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    model = Student
    template_name = 'students/student_form.html'
    fields = ['first_name', 'last_name', 'phone', 'birth_date', 'address', 'is_active']
    success_url = reverse_lazy('students:student_list')
