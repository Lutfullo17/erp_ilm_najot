from django import forms
from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin
from users1.views import AdminAccessRequiredMixin
from groups_app.models import Group, GroupStudent
from .models import Student


class StudentQuickForm(forms.ModelForm):
    full_name = forms.CharField(label='Ism-familiya', required=True)

    class Meta:
        model = Student
        fields = ['phone', 'parent_phone', 'birth_date', 'gender', 'status']
        widgets = {
            'birth_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields['full_name'].initial = f"{self.instance.first_name} {self.instance.last_name}".strip()

    def save(self, commit=True):
        student = super().save(commit=False)
        full_name = self.cleaned_data.get('full_name', '').strip()
        parts = full_name.split(None, 1)
        student.first_name = parts[0]
        student.last_name = parts[1] if len(parts) > 1 else ''
        if commit:
            student.save()
        return student


class StudentListView(LoginRequiredMixin, AdminAccessRequiredMixin, ListView):
    model = Student
    template_name = 'students/student_list.html'
    context_object_name = 'students'
    paginate_by = 20

    def get_queryset(self):
        from django.db.models import Max
        query = self.request.GET.get('q')
        qs = Student.objects.filter(is_active=True).annotate(
            last_payment=Max('payments__payment_date')
        ).prefetch_related('groupstudent_set__group__teacher').order_by('-created_at')
        if query:
            return qs.filter(
                Q(first_name__icontains=query) |
                Q(last_name__icontains=query) |
                Q(phone__icontains=query)
            )
        return qs


class StudentDetailView(LoginRequiredMixin, AdminAccessRequiredMixin, DetailView):
    model = Student
    template_name = 'students/student_detail.html'
    context_object_name = 'student'


class StudentCreateView(LoginRequiredMixin, AdminAccessRequiredMixin, CreateView):
    model = Student
    form_class = StudentQuickForm
    template_name = 'students/student_form.html'
    success_url = reverse_lazy('students:student_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['groups'] = Group.objects.filter(is_active=True).order_by('name')
        return context

    def form_valid(self, form):
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


class StudentUpdateView(LoginRequiredMixin, AdminAccessRequiredMixin, UpdateView):
    model = Student
    form_class = StudentQuickForm
    template_name = 'students/student_form.html'
    success_url = reverse_lazy('students:student_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['groups'] = Group.objects.filter(is_active=True).order_by('name')
        current_group = self.object.groups.filter(groupstudent__is_active=True).first()
        context['current_group_id'] = current_group.id if current_group else None
        return context

    def form_valid(self, form):
        student = form.save()
        group_id = self.request.POST.get('group')
        
        if group_id:
            group = Group.objects.filter(pk=group_id, is_active=True).first()
            if group:
                # Eski guruhlarini deaktivatsiya qilish (agar boshqa guruh tanlangan bo'lsa)
                GroupStudent.objects.filter(student=student, is_active=True).exclude(group=group).update(is_active=False)
                # Yangisini yaratish yoki faollashtirish
                gs, created = GroupStudent.objects.get_or_create(group=group, student=student)
                if not gs.is_active:
                    gs.is_active = True
                    gs.save()
        
        messages.success(self.request, "O'quvchi ma'lumotlari yangilandi!")
        return redirect(self.success_url)


from django.views.decorators.http import require_http_methods
from django.utils import timezone
from users1.services import validate_student_deletion
from users1.views import create_audit_log

@require_http_methods(['POST'])
def delete_student(request, pk):
    if not request.user.is_authenticated or not request.user.is_director:
        messages.error(request, "Faqat Director o'quvchilarni o'chira oladi.")
        return redirect('students:student_list')
    student = get_object_or_404(Student, pk=pk)

    # Validation
    is_valid, error_msg = validate_student_deletion(student)
    if not is_valid:
        messages.error(request, error_msg)
        return redirect('students:student_list')

    # Soft Delete
    student.is_deleted = True
    student.deleted_at = timezone.now()
    student.deleted_by = request.user
    student.is_active = False
    student.save()

    create_audit_log(request, f"O'quvchi o'chirildi: {student.first_name} {student.last_name}")
    messages.success(request, f"{student.first_name} {student.last_name} o'chirildi.")
    return redirect('students:student_list')
