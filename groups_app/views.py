from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse_lazy
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
    fields = ['name', 'monthly_fee', 'teacher', 'start_date', 'is_active']
    success_url = reverse_lazy('groups_app:group_list')

class GroupUpdateView(LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    model = Group
    template_name = 'groups_app/group_form.html'
    fields = ['name', 'monthly_fee', 'teacher', 'start_date', 'is_active']
    success_url = reverse_lazy('groups_app:group_list')

def add_student_to_group(request, pk):
    group = get_object_or_404(Group, pk=pk)
    if request.method == 'POST':
        student_id = request.POST.get('student_id')
        if student_id:
            student = get_object_or_404(Student, pk=student_id)
            GroupStudent.objects.get_or_create(group=group, student=student, defaults={'is_active': True})
    return redirect('groups_app:group_detail', pk=pk)
