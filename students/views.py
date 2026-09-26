from django import forms
from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin
from users1.views import AdminAccessRequiredMixin
from groups_app.models import Group, GroupStudent
from .models import Student, Parent


def normalize_phone_digits(phone):
    """Telefon raqamdan faqat raqamlarni olib, oxirgi 9 tasini qaytaradi."""
    digits = ''.join(ch for ch in str(phone or '') if ch.isdigit())
    if len(digits) == 9:
        digits = '998' + digits
    return digits


def get_or_create_parent(parent_phone, first_name='', last_name=''):
    """Telefon raqami bo'yicha Parent yaratadi yoki mavjudinisini qaytaradi."""
    if not parent_phone or not parent_phone.strip():
        return None
    phone = normalize_phone_digits(parent_phone)
    if len(phone) < 9:
        return None
    parent, _ = Parent.objects.get_or_create(
        phone=phone,
        defaults={'first_name': first_name, 'last_name': last_name}
    )
    return parent


class StudentQuickForm(forms.ModelForm):
    full_name = forms.CharField(label='Ism-familiya', required=True)

    class Meta:
        model = Student
        fields = ['phone', 'parent_phone', 'birth_date', 'gender', 'status',
                  'has_discount', 'discount_type', 'discount_value']
        widgets = {
            'birth_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields['full_name'].initial = f"{self.instance.first_name} {self.instance.last_name}".strip()

    def clean_discount_value(self):
        has_discount = self.cleaned_data.get('has_discount')
        discount_type = self.cleaned_data.get('discount_type')
        discount_value = self.cleaned_data.get('discount_value', 0) or 0
        if has_discount:
            if discount_value <= 0:
                raise forms.ValidationError("Chegirma qiymati 0 dan katta bo'lishi kerak.")
            if discount_type == 'PERCENTAGE' and discount_value > 100:
                raise forms.ValidationError("Foiz chegirma 100% dan oshmasligi kerak.")
        return discount_value

    def save(self, commit=True):
        student = super().save(commit=False)
        full_name = self.cleaned_data.get('full_name', '').strip()
        parts = full_name.split(None, 1)
        student.first_name = parts[0]
        student.last_name = parts[1] if len(parts) > 1 else ''
        # Agar chegirma yo'q bo'lsa, qiymatlarni tozalash
        if not student.has_discount:
            student.discount_value = 0

        # Ota-ona bilan bog'lash
        parent_phone = self.cleaned_data.get('parent_phone', '')
        if parent_phone:
            parent = get_or_create_parent(parent_phone, student.first_name, student.last_name)
            if parent:
                student.parent = parent

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
                # .update() emas, .save(): signal chiqqan sanani yozadi va balanslarni qayta hisoblaydi
                for old_gs in GroupStudent.objects.filter(student=student, is_active=True).exclude(group=group):
                    old_gs.is_active = False
                    old_gs.save()
                # Yangisini yaratish yoki faollashtirish
                gs, created = GroupStudent.objects.get_or_create(group=group, student=student)
                if not gs.is_active:
                    gs.is_active = True
                    gs.save()
        
        messages.success(self.request, "O'quvchi ma'lumotlari yangilandi!")
        return redirect(self.success_url)


from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.http import JsonResponse
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

    # Guruh a'zolarini avtomatik deaktivatsiya qilish
    deactivated = 0
    for gs in GroupStudent.objects.filter(student=student, is_active=True):
        gs.is_active = False
        gs.save()
        deactivated += 1

    msg = f"{student.first_name} {student.last_name} o'chirildi."
    if deactivated:
        msg += f" ({deactivated} ta guruhdan chiqarildi)"

    create_audit_log(request, f"O'quvchi o'chirildi: {student.first_name} {student.last_name}")
    messages.success(request, msg)
    return redirect('students:student_list')


@require_http_methods(['GET'])
def check_parent_phone(request):
    """Ota-ona telefon raqami bilan bog'langan boshqa farzandlarni tekshirish."""
    if not request.user.is_authenticated or not request.user.is_admin_access:
        return JsonResponse({'siblings': []})

    phone = request.GET.get('phone', '').strip()
    if not phone:
        return JsonResponse({'siblings': []})

    # Telefon raqamini normalizatsiya qilish
    digits = ''.join(ch for ch in phone if ch.isdigit())
    
    # Agar raqam +998 bilan boshlansa, 998ni olib tashlaymiz
    if len(digits) == 12 and digits.startswith('998'):
        search_digits = digits[3:]  # 998ni olib tashlash
    elif len(digits) == 9:
        search_digits = digits
    else:
        return JsonResponse({'siblings': []})

    # Avval Parent modelidan qidiramiz
    parent = Parent.objects.filter(phone__contains=search_digits).first()
    if parent:
        siblings = Student.objects.filter(
            parent=parent,
            is_active=True,
        ).values_list('first_name', 'last_name')
        sibling_names = [f"{fn} {ln}".strip() for fn, ln in siblings]
        return JsonResponse({'siblings': sibling_names})

    # Agar Parent topilmasa, parent_phone bo'yicha qidiramiz
    siblings = Student.objects.filter(
        parent_phone__contains=search_digits,
        is_active=True,
    ).values_list('first_name', 'last_name')

    sibling_names = [f"{fn} {ln}".strip() for fn, ln in siblings]
    return JsonResponse({'siblings': sibling_names})


@require_http_methods(['GET'])
def get_student_debt(request, pk):
    """O'quvchining jami qarzini qaytaradi."""
    if not request.user.is_authenticated or not request.user.is_admin_access:
        return JsonResponse({'detail': "Ruxsat yo'q."}, status=403)

    student = get_object_or_404(Student, pk=pk)
    from payments.models import StudentMonthBalance
    from django.db import models as db_models

    total_debt = StudentMonthBalance.objects.debts().filter(
        student=student,
    ).aggregate(
        total=db_models.Sum(db_models.F('required_amount') - db_models.F('paid_amount'))
    )['total'] or 0

    return JsonResponse({
        'student_name': f"{student.first_name} {student.last_name}",
        'total_debt': str(total_debt),
        'has_debt': float(total_debt) > 0,
    })

