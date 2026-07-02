import json as json_module
import os
from collections import defaultdict

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.views import LoginView
from django.contrib.auth import update_session_auth_hash
from django.http import JsonResponse
from django.shortcuts import redirect, get_object_or_404, render
from django.views.generic import TemplateView, ListView, CreateView, UpdateView
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from django.urls import reverse_lazy
from django import forms
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Sum
from django.utils import timezone

from students.models import Student
from payments.models import StudentMonthBalance, MonthBalanceStatus, PaymentTransaction
from payments.services import first_day_of_month
from attendance.models import AttendanceRecord, AttendanceSession
from groups_app.models import Group, GroupStudent
from bot.models import TelegramAppeal, TelegramUser
from .models import (
    User,
    AuditLog,
    TeacherPenalty,
    MissedAttendanceAlert,
    ScheduleChangeRequest,
)


# ---------------------------------------------------------------------------
# Helper: IP address
# ---------------------------------------------------------------------------
def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0]
    return request.META.get('REMOTE_ADDR')


def create_audit_log(request, action, target_user=None):
    AuditLog.objects.create(
        user=request.user if request.user.is_authenticated else None,
        target_user=target_user,
        action=action,
        ip_address=get_client_ip(request),
    )


def _parse_lesson_days(lesson_days):
    return {d.strip() for d in lesson_days.split(',') if d.strip()} if lesson_days else set()


def _times_overlap(start_a, end_a, start_b, end_b):
    return start_a < end_b and end_a > start_b


def _compute_end_time(group):
    if group.end_time:
        return group.end_time
    if group.lesson_time and group.duration is not None:
        import datetime
        hours = int(group.duration)
        minutes = int((group.duration - hours) * 60)
        return (datetime.datetime.combine(datetime.date.today(), group.lesson_time) + datetime.timedelta(hours=hours, minutes=minutes)).time()
    return None


def _duration_to_decimal_hours(start_time, end_time):
    import datetime
    start_dt = datetime.datetime.combine(datetime.date.today(), start_time)
    end_dt = datetime.datetime.combine(datetime.date.today(), end_time)
    diff = end_dt - start_dt
    return diff.seconds / 3600


def _start_of_week(value):
    return value - timezone.timedelta(days=value.weekday())


def _get_week_override(group, week_start):
    return ScheduleChangeRequest.objects.filter(
        group=group,
        status=ScheduleChangeRequest.Status.APPROVED,
        effective_week_start=week_start,
    ).order_by('-submitted_at').first()


# ---------------------------------------------------------------------------
# Forms
# ---------------------------------------------------------------------------
class TeacherCreateForm(forms.ModelForm):
    password1 = forms.CharField(label='Parol', widget=forms.PasswordInput, min_length=8)
    password2 = forms.CharField(label='Parolni tasdiqlash', widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ['username', 'phone']

    def clean_password2(self):
        p1 = self.cleaned_data.get('password1')
        p2 = self.cleaned_data.get('password2')
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError("Parollar mos kelmaydi.")
        return p2

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password1'])
        user.role = 'TEACHER'
        if commit:
            user.save()
        return user


class ScheduleChangeRequestForm(forms.ModelForm):
    DAY_CHOICES = [
        ('Dushanba', 'Dushanba'),
        ('Seshanba', 'Seshanba'),
        ('Chorshanba', 'Chorshanba'),
        ('Payshanba', 'Payshanba'),
        ('Juma', 'Juma'),
        ('Shanba', 'Shanba'),
        ('Yakshanba', 'Yakshanba'),
    ]

    new_day = forms.ChoiceField(choices=DAY_CHOICES, label='Yangi dars kuni')
    new_start_time = forms.TimeField(
        widget=forms.TextInput(attrs={
            'type': 'text',
            'placeholder': 'HH:MM',
            'pattern': '([01]\\d|2[0-3]):[0-5]\\d',
            'inputmode': 'numeric',
            'maxlength': '5',
        }),
        label='Yangi boshlanish vaqti',
        input_formats=['%H:%M'],
        help_text='Format: HH:MM'
    )
    new_end_time = forms.TimeField(
        widget=forms.TextInput(attrs={
            'type': 'text',
            'placeholder': 'HH:MM',
            'pattern': '([01]\\d|2[0-3]):[0-5]\\d',
            'inputmode': 'numeric',
            'maxlength': '5',
        }),
        label='Yangi tugash vaqti',
        input_formats=['%H:%M'],
        help_text='Format: HH:MM'
    )
    reason = forms.CharField(widget=forms.Textarea(attrs={'rows': 4}), label='Sabab')

    class Meta:
        model = ScheduleChangeRequest
        fields = ['new_day', 'new_start_time', 'new_end_time', 'reason']

    def __init__(self, *args, group=None, teacher=None, old_day=None, old_start_time=None, old_end_time=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.group = group
        self.teacher = teacher
        self.old_day = old_day
        self.old_start_time = old_start_time
        self.old_end_time = old_end_time

        if group is not None:
            self.fields['new_day'].initial = old_day
            self.fields['new_start_time'].initial = old_start_time.strftime('%H:%M') if old_start_time else ''
            self.fields['new_end_time'].initial = old_end_time.strftime('%H:%M') if old_end_time else ''

    def clean(self):
        cleaned_data = super().clean()
        new_day = cleaned_data.get('new_day')
        new_start = cleaned_data.get('new_start_time')
        new_end = cleaned_data.get('new_end_time')

        if new_start and new_end and new_start >= new_end:
            raise ValidationError('Yangi boshlanish vaqti tugash vaqtidan kichik bo‘lishi kerak.')

        if self.group is None or self.teacher is None:
            return cleaned_data

        if new_day == self.old_day and new_start == self.old_start_time and new_end == self.old_end_time:
            raise ValidationError('Yangi vaqt hozirgi vaqt bilan bir xil. Iltimos, boshqa vaqt tanlang.')

        # O'qituvchi konfliktlari
        conflicts = Group.objects.filter(
            teacher=self.teacher,
            is_active=True,
            lesson_time__isnull=False,
            end_time__isnull=False
        ).exclude(pk=self.group.pk)

        for other in conflicts:
            other_days = _parse_lesson_days(other.lesson_days)
            if new_day in other_days and _times_overlap(new_start, new_end, other.lesson_time, other.end_time):
                raise ValidationError('Siz tanlagan vaqtda boshqa guruhga dars o‘tasiz.')

        # Xona konfliktlari
        if self.group.room:
            room_conflicts = Group.objects.filter(
                room=self.group.room,
                is_active=True,
                lesson_time__isnull=False,
                end_time__isnull=False
            ).exclude(pk=self.group.pk)
            for other in room_conflicts:
                other_days = _parse_lesson_days(other.lesson_days)
                if new_day in other_days and _times_overlap(new_start, new_end, other.lesson_time, other.end_time):
                    raise ValidationError('Siz tanlagan xonada boshqa guruh band.')

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.teacher = self.teacher
        instance.group = self.group
        instance.old_day = self.old_day
        instance.old_start_time = self.old_start_time
        instance.old_end_time = self.old_end_time
        instance.status = ScheduleChangeRequest.Status.PENDING
        if commit:
            instance.save()
        return instance


# ---------------------------------------------------------------------------
# RBAC Mixins
# ---------------------------------------------------------------------------
class TeacherRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.is_teacher and not self.request.user.is_blocked

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return redirect('users1:login')
        if self.request.user.is_blocked:
            messages.error(self.request, "Sizning akkauntingiz bloklangan. Director bilan bog'laning.")
            return redirect('users1:login')
        return redirect('users1:admin_dashboard')


class DirectorRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.is_director

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return redirect('users1:login')
        if self.request.user.is_administrator_role:
            return redirect('users1:administrator_dashboard')
        return redirect('users1:teacher_dashboard')


class AdministratorRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.is_administrator_role and not self.request.user.is_blocked

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return redirect('users1:login')
        if self.request.user.is_blocked:
            messages.error(self.request, "Sizning akkauntingiz bloklangan. Director bilan bog'laning.")
            return redirect('users1:login')
        if self.request.user.is_director:
            return redirect('users1:admin_dashboard')
        return redirect('users1:teacher_dashboard')


class AdminAccessRequiredMixin(UserPassesTestMixin):
    """Access for either Director or Administrator"""
    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.is_admin_access and not self.request.user.is_blocked

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return redirect('users1:login')
        if self.request.user.is_blocked:
            messages.error(self.request, "Sizning akkauntingiz bloklangan.")
            return redirect('users1:login')
        return redirect('users1:teacher_dashboard')


# ---------------------------------------------------------------------------
# Root redirect
# ---------------------------------------------------------------------------
def index(request):
    if request.user.is_authenticated:
        if request.user.is_director:
            return redirect('users1:admin_dashboard')
        if request.user.is_administrator_role:
            return redirect('users1:administrator_dashboard')
        if request.user.is_teacher:
            return redirect('users1:teacher_dashboard')
    return redirect('users1:login')


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------
class RoleLoginView(LoginView):
    template_name = 'users1/login.html'
    redirect_authenticated_user = True

    def form_valid(self, form):
        user = form.get_user()
        if user.is_blocked:
            messages.error(self.request, "Sizning akkauntingiz bloklangan. Director bilan bog'laning.")
            return self.form_invalid(form)
        return super().form_valid(form)

    def get_success_url(self):
        user = self.request.user
        if user.is_director:
            return '/users/admin/'
        if user.is_administrator_role:
            return '/users/administrator/'
        if user.is_teacher:
            return '/users/teacher/'
        return '/users/'


# ---------------------------------------------------------------------------
# Director Profile
# ---------------------------------------------------------------------------
class DirectorProfileView(LoginRequiredMixin, DirectorRequiredMixin, TemplateView):
    template_name = 'users1/director_profile.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['audit_logs'] = AuditLog.objects.filter(
            user=self.request.user
        ).order_by('-created_at')[:20]
        context['administrators'] = User.objects.filter(role=User.Role.ADMINISTRATOR).order_by('last_name', 'first_name')
        return context


@require_http_methods(['POST'])
def director_change_login(request):
    """Director o'z loginini o'zgartiradi"""
    if not request.user.is_authenticated or not request.user.is_director:
        return JsonResponse({'error': 'Ruxsat yo\'q'}, status=403)

    try:
        data = json_module.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Noto\'g\'ri ma\'lumot'}, status=400)

    new_username = data.get('username', '').strip()
    if not new_username:
        return JsonResponse({'error': 'Login kiritilmagan'}, status=400)

    if User.objects.filter(username=new_username).exclude(pk=request.user.pk).exists():
        return JsonResponse({'error': 'Bu login allaqachon band'}, status=400)

    old_username = request.user.username
    request.user.username = new_username
    request.user.save()
    create_audit_log(request, f"Login o'zgartirildi: {old_username} → {new_username}", target_user=request.user)
    return JsonResponse({'ok': True, 'message': 'Login muvaffaqiyatli o\'zgartirildi'})


@require_http_methods(['POST'])
def director_update_info(request):
    """Director o'zining Ism, Familiya va Telefon raqamini o'zgartiradi"""
    if not request.user.is_authenticated or not request.user.is_director:
        return JsonResponse({'error': 'Ruxsat yo\'q'}, status=403)

    try:
        data = json_module.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Noto\'g\'ri ma\'lumot'}, status=400)

    first_name = data.get('first_name', '').strip()
    last_name = data.get('last_name', '').strip()
    phone = data.get('phone', '').strip()

    if not first_name:
        return JsonResponse({'error': 'Ism kiritilishi shart'}, status=400)

    request.user.first_name = first_name
    request.user.last_name = last_name
    request.user.phone = phone
    request.user.save()

    create_audit_log(request, "Profil ma'lumotlari yangilandi", target_user=request.user)
    return JsonResponse({'ok': True, 'message': 'Ma\'lumotlar muvaffaqiyatli yangilandi'})


@require_http_methods(['POST'])
def director_change_password(request):
    """Director o'z parolini o'zgartiradi"""
    if not request.user.is_authenticated or not request.user.is_director:
        return JsonResponse({'error': 'Ruxsat yo\'q'}, status=403)

    try:
        data = json_module.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Noto\'g\'ri ma\'lumot'}, status=400)

    old_password = data.get('old_password', '')
    new_password = data.get('new_password', '')
    confirm_password = data.get('confirm_password', '')

    if not request.user.check_password(old_password):
        return JsonResponse({'error': 'Eski parol noto\'g\'ri'}, status=400)

    if len(new_password) < 6:
        return JsonResponse({'error': 'Yangi parol kamida 6 belgidan iborat bo\'lishi kerak'}, status=400)

    if new_password != confirm_password:
        return JsonResponse({'error': 'Yangi parollar mos kelmaydi'}, status=400)

    request.user.set_password(new_password)
    request.user.save()
    update_session_auth_hash(request, request.user)
    create_audit_log(request, "Parol o'zgartirildi", target_user=request.user)
    return JsonResponse({'ok': True, 'message': 'Parol muvaffaqiyatli o\'zgartirildi'})


@require_http_methods(['POST'])
def director_change_photo(request):
    """Director profil rasmini o'zgartiradi"""
    if not request.user.is_authenticated or not request.user.is_director:
        return JsonResponse({'error': 'Ruxsat yo\'q'}, status=403)

    photo = request.FILES.get('photo')
    if not photo:
        return JsonResponse({'error': 'Rasm tanlanmagan'}, status=400)

    # Old photo sil
    if request.user.photo:
        try:
            old_path = request.user.photo.path
            if os.path.exists(old_path):
                os.remove(old_path)
        except Exception:
            pass

    request.user.photo = photo
    request.user.save()
    create_audit_log(request, "Profil rasmi yangilandi", target_user=request.user)
    return JsonResponse({'ok': True, 'photo_url': request.user.photo.url, 'message': 'Profil rasmi yangilandi'})


# ---------------------------------------------------------------------------
# Administrator Account Management (only Director can manage)
# ---------------------------------------------------------------------------
class AdministratorListView(LoginRequiredMixin, DirectorRequiredMixin, ListView):
    template_name = 'users1/administrator_list.html'
    context_object_name = 'administrators'

    def get_queryset(self):
        return User.objects.filter(role=User.Role.ADMINISTRATOR).order_by('last_name', 'first_name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['total_admins'] = User.objects.filter(role=User.Role.ADMINISTRATOR).count()
        return context


class AdministratorCreateView(LoginRequiredMixin, DirectorRequiredMixin, TemplateView):
    template_name = 'users1/administrator_form.html'

    def post(self, request):
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        phone = request.POST.get('phone', '').strip()

        if not username or not password:
            messages.error(request, "Login va parol majburiy.")
            return redirect('users1:administrator_list')

        if User.objects.filter(username=username).exists():
            messages.error(request, "Bu login allaqachon mavjud.")
            return redirect('users1:administrator_list')

        user = User(
            username=username,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            role=User.Role.ADMINISTRATOR,
        )
        user.set_password(password)
        user.save()
        create_audit_log(request, f"Administrator yaratildi: {username}", target_user=user)
        messages.success(request, f"Administrator '{username}' muvaffaqiyatli yaratildi!")
        return redirect('users1:administrator_list')


@require_http_methods(['POST'])
def director_change_admin_login(request, pk):
    """Director administrator loginini o'zgartiradi"""
    if not request.user.is_authenticated or not request.user.is_director:
        return JsonResponse({'error': 'Ruxsat yo\'q'}, status=403)

    admin_user = get_object_or_404(User, pk=pk, role=User.Role.ADMINISTRATOR)

    try:
        data = json_module.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Noto\'g\'ri ma\'lumot'}, status=400)

    new_username = data.get('username', '').strip()
    if not new_username:
        return JsonResponse({'error': 'Login kiritilmagan'}, status=400)

    if User.objects.filter(username=new_username).exclude(pk=pk).exists():
        return JsonResponse({'error': 'Bu login allaqachon band'}, status=400)

    old_username = admin_user.username
    admin_user.username = new_username
    admin_user.save()
    create_audit_log(request, f"Administrator logini o'zgartirildi: {old_username} → {new_username}", target_user=admin_user)
    return JsonResponse({'ok': True, 'message': f'Login muvaffaqiyatli yangilandi'})


@require_http_methods(['POST'])
def director_reset_admin_password(request, pk):
    """Director administrator parolini tiklaydi"""
    if not request.user.is_authenticated or not request.user.is_director:
        return JsonResponse({'error': 'Ruxsat yo\'q'}, status=403)

    admin_user = get_object_or_404(User, pk=pk, role=User.Role.ADMINISTRATOR)

    try:
        data = json_module.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Noto\'g\'ri ma\'lumot'}, status=400)

    new_password = data.get('new_password', '').strip()
    if len(new_password) < 6:
        return JsonResponse({'error': 'Parol kamida 6 belgidan iborat bo\'lishi kerak'}, status=400)

    admin_user.set_password(new_password)
    admin_user.save()
    create_audit_log(request, f"Administrator paroli tiklandi: {admin_user.username}", target_user=admin_user)
    return JsonResponse({'ok': True, 'message': 'Parol muvaffaqiyatli tiklandi'})


@require_http_methods(['POST'])
def director_toggle_admin_block(request, pk):
    """Director administrator akkauntini bloklaydi/faollashtiradi"""
    if not request.user.is_authenticated or not request.user.is_director:
        return JsonResponse({'error': 'Ruxsat yo\'q'}, status=403)

    admin_user = get_object_or_404(User, pk=pk, role=User.Role.ADMINISTRATOR)
    admin_user.is_blocked = not admin_user.is_blocked
    admin_user.save()

    action = "bloklandi" if admin_user.is_blocked else "faollashtirildi"
    create_audit_log(request, f"Administrator akkaunti {action}: {admin_user.username}", target_user=admin_user)
    return JsonResponse({
        'ok': True,
        'is_blocked': admin_user.is_blocked,
        'message': f"Akkount {action}"
    })


# ---------------------------------------------------------------------------
# Teacher Account Management
# ---------------------------------------------------------------------------
class TeacherListView(LoginRequiredMixin, DirectorRequiredMixin, ListView):
    template_name = 'users1/teacher_list.html'
    context_object_name = 'teachers'

    def get_queryset(self):
        return User.objects.filter(role='TEACHER', is_deleted=False).order_by('last_name', 'first_name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['total_teachers'] = User.objects.filter(role='TEACHER', is_deleted=False).count()
        return context


class TeacherCreateView(LoginRequiredMixin, DirectorRequiredMixin, CreateView):
    template_name = 'users1/teacher_form.html'
    form_class = TeacherCreateForm
    context_object_name = 'teacher_obj'
    success_url = reverse_lazy('users1:teacher_list')

    def form_valid(self, form):
        full_name = self.request.POST.get('full_name', '').strip()
        if not full_name:
            form.add_error(None, "Ism-familiyani kiriting.")
            return self.form_invalid(form)

        parts = full_name.split(None, 1)
        form.instance.first_name = parts[0]
        form.instance.last_name = parts[1] if len(parts) > 1 else ''

        user = form.save()
        create_audit_log(self.request, f"O'qituvchi yaratildi: {user.username}", target_user=user)
        messages.success(self.request, "O'qituvchi muvaffaqiyatli qo'shildi!")
        return redirect(self.success_url)


class TeacherUpdateView(LoginRequiredMixin, DirectorRequiredMixin, UpdateView):
    template_name = 'users1/teacher_form.html'
    model = User
    context_object_name = 'teacher_obj'
    fields = ['username', 'phone']
    success_url = reverse_lazy('users1:teacher_list')

    def get_object(self, queryset=None):
        return get_object_or_404(User, pk=self.kwargs['pk'], role='TEACHER')

    def form_valid(self, form):
        full_name = self.request.POST.get('full_name', '').strip()
        if not full_name:
            form.add_error(None, "Ism-familiyani kiriting.")
            return self.form_invalid(form)

        parts = full_name.split(None, 1)
        self.object.first_name = parts[0]
        self.object.last_name = parts[1] if len(parts) > 1 else ''

        # Login tekshiruvi
        new_username = form.cleaned_data.get('username')
        if User.objects.filter(username=new_username).exclude(pk=self.object.pk).exists():
            form.add_error('username', "Bu login allaqachon band.")
            return self.form_invalid(form)

        # Parol o'zgartirish
        new_password = self.request.POST.get('new_password', '').strip()
        new_password2 = self.request.POST.get('new_password2', '').strip()
        if new_password:
            if len(new_password) < 6:
                form.add_error(None, "Parol kamida 6 belgidan iborat bo'lishi kerak.")
                return self.form_invalid(form)
            if new_password != new_password2:
                form.add_error(None, "Parollar mos kelmaydi.")
                return self.form_invalid(form)
            self.object.set_password(new_password)

        user = form.save()
        create_audit_log(self.request, f"O'qituvchi ma'lumotlari yangilandi: {user.username}", target_user=user)
        messages.success(self.request, "O'qituvchi ma'lumotlari yangilandi!")
        return redirect('users1:teacher_list')


from users1.services import validate_teacher_deletion

@require_http_methods(['POST'])
def delete_teacher(request, pk):
    teacher = get_object_or_404(User, pk=pk, role='TEACHER')

    # Validation
    is_valid, error_msg = validate_teacher_deletion(teacher)
    if not is_valid:
        messages.error(request, error_msg)
        return redirect('users1:teacher_list')

    # Soft Delete
    teacher.is_deleted = True
    teacher.deleted_at = timezone.now()
    teacher.deleted_by = request.user
    teacher.is_active = False # Assuming we want to also deactivate the user
    teacher.save()

    create_audit_log(request, f"O'qituvchi o'chirildi: {teacher.username}", target_user=teacher)
    messages.success(request, f"{teacher.get_full_name()} o'chirildi.")
    return redirect('users1:teacher_list')


@require_http_methods(['POST'])
def director_change_teacher_login(request, pk):
    """Director teacher loginini o'zgartiradi"""
    if not request.user.is_authenticated or not request.user.is_director:
        return JsonResponse({'error': 'Ruxsat yo\'q'}, status=403)

    teacher = get_object_or_404(User, pk=pk, role=User.Role.TEACHER)

    try:
        data = json_module.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Noto\'g\'ri ma\'lumot'}, status=400)

    new_username = data.get('username', '').strip()
    if not new_username:
        return JsonResponse({'error': 'Login kiritilmagan'}, status=400)

    if User.objects.filter(username=new_username).exclude(pk=pk).exists():
        return JsonResponse({'error': 'Bu login allaqachon band'}, status=400)

    old_username = teacher.username
    teacher.username = new_username
    teacher.save()
    create_audit_log(request, f"O'qituvchi logini o'zgartirildi: {old_username} → {new_username}", target_user=teacher)
    return JsonResponse({'ok': True, 'message': 'Login muvaffaqiyatli yangilandi'})


@require_http_methods(['POST'])
def director_reset_teacher_password(request, pk):
    """Director teacher parolini tiklaydi"""
    if not request.user.is_authenticated or not request.user.is_director:
        return JsonResponse({'error': 'Ruxsat yo\'q'}, status=403)

    teacher = get_object_or_404(User, pk=pk, role=User.Role.TEACHER)

    try:
        data = json_module.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Noto\'g\'ri ma\'lumot'}, status=400)

    new_password = data.get('new_password', '').strip()
    if len(new_password) < 6:
        return JsonResponse({'error': 'Parol kamida 6 belgidan iborat bo\'lishi kerak'}, status=400)

    teacher.set_password(new_password)
    teacher.save()
    create_audit_log(request, f"O'qituvchi paroli tiklandi: {teacher.username}", target_user=teacher)
    return JsonResponse({'ok': True, 'message': 'Parol muvaffaqiyatli tiklandi'})


# ---------------------------------------------------------------------------
# Teacher Management (Director sees detail of each teacher)
# ---------------------------------------------------------------------------
class TeacherDetailView(LoginRequiredMixin, DirectorRequiredMixin, TemplateView):
    template_name = 'users1/teacher_detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        teacher = get_object_or_404(User, pk=self.kwargs['pk'], role=User.Role.TEACHER)
        context['teacher'] = teacher
        context['teacher_groups'] = teacher.teaching_groups.filter(is_active=True)
        context['penalties'] = TeacherPenalty.objects.filter(teacher=teacher).order_by('-created_at')[:20]
        context['total_penalty_points'] = TeacherPenalty.objects.filter(teacher=teacher).aggregate(
            total=Sum('points')
        )['total'] or 0
        context['audit_logs'] = AuditLog.objects.filter(target_user=teacher).order_by('-created_at')[:20]
        return context


# ---------------------------------------------------------------------------
# Penalty System - Director Views
# ---------------------------------------------------------------------------
class PenaltyListView(LoginRequiredMixin, DirectorRequiredMixin, TemplateView):
    template_name = 'users1/penalty_list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        this_month = today.month
        this_year = today.year

        context['penalties'] = TeacherPenalty.objects.select_related('teacher', 'group').order_by('-created_at')[:50]
        context['teachers'] = User.objects.filter(role=User.Role.TEACHER, is_deleted=False)

        # Teacher-based stats (Optimized)
        from django.db.models import Case, When, DecimalField
        teacher_stats_qs = User.objects.filter(
            role=User.Role.TEACHER, 
            is_deleted=False
        ).annotate(
            total_points=Sum('penalties__points'),
            monthly_points=Sum(
                Case(
                    When(
                        penalties__created_at__year=this_year,
                        penalties__created_at__month=this_month,
                        then='penalties__points'
                    ),
                    default=0,
                    output_field=DecimalField()
                )
            )
        ).order_by('total_points')

        context['teacher_stats'] = [
            {
                'teacher': t,
                'total_points': t.total_points or 0,
                'monthly_points': t.monthly_points or 0,
            }
            for t in teacher_stats_qs
        ]

        context['monthly_total'] = TeacherPenalty.objects.filter(
            created_at__year=this_year,
            created_at__month=this_month,
        ).aggregate(total=Sum('points'))['total'] or 0

        context['missed_alerts'] = MissedAttendanceAlert.objects.filter(
            status=MissedAttendanceAlert.Status.PENDING
        ).select_related('teacher', 'group').order_by('-created_at')[:20]

        # Ketma-ket 3 ta darsda davomat olinmagan teacherlar
        teachers_with_3_consecutive = []
        for teacher in User.objects.filter(role=User.Role.TEACHER, is_deleted=False):
            recent_alerts = MissedAttendanceAlert.objects.filter(
                teacher=teacher,
                status__in=[MissedAttendanceAlert.Status.CAME, MissedAttendanceAlert.Status.NOT_CAME],
                penalty_applied=True,
            ).order_by('-lesson_date')[:3]
            if len(recent_alerts) >= 3:
                teachers_with_3_consecutive.append({'teacher': teacher})
        context['teachers_with_3_consecutive'] = teachers_with_3_consecutive
        context['teachers_with_consecutive'] = teachers_with_3_consecutive  # alias

        # Today's missed teachers
        context['today_missed_teachers'] = MissedAttendanceAlert.objects.filter(
            lesson_date=today
        ).select_related('teacher', 'group').order_by('-created_at')

        return context


@require_http_methods(['POST'])
def director_add_penalty(request, teacher_pk):
    """Director qo'lda jarima beradi"""
    if not request.user.is_authenticated or not request.user.is_director:
        return JsonResponse({'error': 'Ruxsat yo\'q'}, status=403)

    teacher = get_object_or_404(User, pk=teacher_pk, role=User.Role.TEACHER)

    try:
        data = json_module.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Noto\'g\'ri ma\'lumot'}, status=400)

    points = data.get('points', 0)
    reason = data.get('reason', '').strip()

    if not reason:
        return JsonResponse({'error': 'Sabab kiritilmagan'}, status=400)

    try:
        points = int(points)
    except (TypeError, ValueError):
        return JsonResponse({'error': 'Ball noto\'g\'ri'}, status=400)

    penalty = TeacherPenalty.objects.create(
        teacher=teacher,
        date=timezone.localdate(),
        reason=reason,
        points=points,
        penalty_type=TeacherPenalty.PenaltyType.MANUAL,
        is_manual=True,
        given_by=request.user,
    )
    create_audit_log(request, f"Qo'lda jarima berildi: {teacher.username}, {points} ball, sabab: {reason}", target_user=teacher)
    return JsonResponse({'ok': True, 'message': f'{abs(points)} ball jarima berildi'})


@require_http_methods(['POST'])
def resolve_missed_alert(request, alert_pk):
    """Director yoki Administrator missed attendance alertni hal qiladi"""
    if not request.user.is_authenticated or not request.user.is_admin_access:
        return JsonResponse({'error': 'Ruxsat yo\'q'}, status=403)

    alert = get_object_or_404(MissedAttendanceAlert, pk=alert_pk, status=MissedAttendanceAlert.Status.PENDING)

    try:
        data = json_module.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Noto\'g\'ri ma\'lumot'}, status=400)

    decision = data.get('decision')  # 'came' yoki 'not_came'

    if decision not in ('came', 'not_came'):
        return JsonResponse({'error': 'Qaror noto\'g\'ri'}, status=400)

    from .penalty_service import apply_penalty_for_alert
    apply_penalty_for_alert(alert, decision, request.user)

    create_audit_log(request, f"Davomat ogohlantirishni hal qilindi: {alert.teacher.username}, {alert.group.name} → {decision}", target_user=alert.teacher)

    return JsonResponse({'ok': True, 'message': 'Xabarnoma hal qilindi va jarima berildi'})


# ---------------------------------------------------------------------------
# Audit Logs
# ---------------------------------------------------------------------------
class AuditLogView(LoginRequiredMixin, DirectorRequiredMixin, TemplateView):
    template_name = 'users1/audit_log.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['logs'] = AuditLog.objects.select_related('user', 'target_user').order_by('-created_at')[:100]
        return context


# ---------------------------------------------------------------------------
# Administrator Profile (read-only)
# ---------------------------------------------------------------------------
class AdministratorProfileView(LoginRequiredMixin, AdministratorRequiredMixin, TemplateView):
    template_name = 'users1/administrator_profile.html'


# ---------------------------------------------------------------------------
# Teacher Profile (read-only)
# ---------------------------------------------------------------------------
class TeacherProfileView(LoginRequiredMixin, TeacherRequiredMixin, TemplateView):
    template_name = 'users1/teacher_profile.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        today = timezone.localdate()
        this_month = today.month
        this_year = today.year

        context['penalties'] = TeacherPenalty.objects.filter(teacher=user).order_by('-created_at')[:10]
        context['total_penalty_points'] = TeacherPenalty.objects.filter(teacher=user).aggregate(
            total=Sum('points')
        )['total'] or 0
        context['monthly_penalty'] = TeacherPenalty.objects.filter(
            teacher=user,
            created_at__year=this_year,
            created_at__month=this_month,
        ).aggregate(total=Sum('points'))['total'] or 0
        return context


# ---------------------------------------------------------------------------
# Teacher Dashboard
# ---------------------------------------------------------------------------
class TeacherDashboardView(LoginRequiredMixin, TeacherRequiredMixin, TemplateView):
    template_name = 'users1/teacher_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        today = timezone.localdate()
        weekday = today.weekday()
        now_time = timezone.localtime().time()

        groups = user.teaching_groups.filter(is_active=True)
        context['groups'] = groups

        context['total_students'] = GroupStudent.objects.filter(
            group__in=groups,
            is_active=True,
            student__is_active=True
        ).count()

        context['today_attendance'] = AttendanceRecord.objects.filter(
            session__teacher=user,
            session__date=today
        ).count()

        from bot.models import TelegramAppeal
        context['pending_appeals_count'] = TelegramAppeal.objects.filter(
            student__groupstudent__group__teacher=user,
            is_resolved=False
        ).count()

        day_names = ['Dushanba', 'Seshanba', 'Chorshanba', 'Payshanba', 'Juma', 'Shanba', 'Yakshanba']
        today_name = day_names[weekday]

        today_lessons = []
        upcoming_lessons = []
        groups_without_attendance = []
        overdue_groups = []
        today_lesson_count = 0

        for group in groups:
            if group.lesson_days and group.lesson_time:
                is_today = today_name in group.lesson_days
                lesson_data = {'group': group, 'time': group.lesson_time, 'days': group.lesson_days}

                if is_today:
                    # Dars holatini aniqlash
                    import datetime
                    if group.end_time:
                        end_time = group.end_time
                    elif group.duration:
                        hours = int(group.duration)
                        minutes = int((group.duration - hours) * 60)
                        td = datetime.timedelta(hours=hours, minutes=minutes)
                        end_time = (datetime.datetime.combine(today, group.lesson_time) + td).time()
                    else:
                        end_time = group.lesson_time

                    if now_time < group.lesson_time:
                        delta = datetime.datetime.combine(today, group.lesson_time) - datetime.datetime.combine(today, now_time)
                        total_mins = int(delta.total_seconds() // 60)
                        hours, mins = divmod(total_mins, 60)
                        lesson_data['lesson_status'] = 'upcoming'
                        lesson_data['time_remaining'] = f"{hours} soat {mins} daqiqa" if hours else f"{mins} daqiqa"
                    elif now_time <= end_time:
                        delta = datetime.datetime.combine(today, end_time) - datetime.datetime.combine(today, now_time)
                        total_mins = int(delta.total_seconds() // 60)
                        hours, mins = divmod(total_mins, 60)
                        lesson_data['lesson_status'] = 'active'
                        lesson_data['time_remaining'] = f"{hours} soat {mins} daqiqa" if hours else f"{mins} daqiqa"
                    else:
                        lesson_data['lesson_status'] = 'ended'
                        lesson_data['time_remaining'] = None
                    today_lesson_count += 1
                    has_session = AttendanceSession.objects.filter(group=group, date=today).exists()

                    if not has_session and group.end_time and now_time > group.end_time:
                        overdue_groups.append(group)
                    elif not has_session and group.end_time and now_time <= group.end_time:
                        groups_without_attendance.append(group)

                    today_lessons.append(lesson_data)
                else:
                    upcoming_lessons.append(lesson_data)

        context['today_lessons'] = today_lessons
        context['upcoming_lessons'] = upcoming_lessons[:5]
        context['today_lesson_count'] = today_lesson_count
        context['groups_without_attendance'] = groups_without_attendance
        context['overdue_groups'] = overdue_groups

        context['recent_schedule_reviews'] = ScheduleChangeRequest.objects.filter(
            teacher=user,
            status__in=[ScheduleChangeRequest.Status.APPROVED, ScheduleChangeRequest.Status.REJECTED],
            reviewed_at__isnull=False
        ).order_by('-reviewed_at')[:5]

        # Penalty info
        context['total_penalty_points'] = TeacherPenalty.objects.filter(teacher=user).aggregate(
            total=Sum('points')
        )['total'] or 0

        return context


class ScheduleChangeRequestCreateView(LoginRequiredMixin, TeacherRequiredMixin, TemplateView):
    template_name = 'users1/schedule_change_request_form.html'

    def get(self, request, *args, **kwargs):
        group = get_object_or_404(
            Group,
            pk=kwargs.get('group_pk'),
            teacher=request.user,
            is_active=True,
        )

        lesson_days = [d.strip() for d in group.lesson_days.split(',') if d.strip()]
        if not lesson_days:
            messages.error(request, 'Guruhning hozirgi dars kuni mavjud emas.')
            return redirect('users1:teacher_schedule')

        old_day = request.GET.get('day')
        if old_day not in lesson_days:
            old_day = lesson_days[0]

        old_start_time = group.lesson_time
        old_end_time = _compute_end_time(group)
        form = ScheduleChangeRequestForm(
            group=group,
            teacher=request.user,
            old_day=old_day,
            old_start_time=old_start_time,
            old_end_time=old_end_time,
        )
        return render(request, self.template_name, {
            'group': group,
            'old_day': old_day,
            'old_start_time': old_start_time,
            'old_end_time': old_end_time,
            'form': form,
        })

    def post(self, request, *args, **kwargs):
        group = get_object_or_404(
            Group,
            pk=kwargs.get('group_pk'),
            teacher=request.user,
            is_active=True,
        )

        lesson_days = [d.strip() for d in group.lesson_days.split(',') if d.strip()]
        if not lesson_days:
            messages.error(request, 'Guruhning hozirgi dars kuni mavjud emas.')
            return redirect('users1:teacher_schedule')

        old_day = request.GET.get('day')
        if old_day not in lesson_days:
            old_day = lesson_days[0]

        old_start_time = group.lesson_time
        old_end_time = _compute_end_time(group)
        form = ScheduleChangeRequestForm(
            request.POST,
            group=group,
            teacher=request.user,
            old_day=old_day,
            old_start_time=old_start_time,
            old_end_time=old_end_time,
        )
        if form.is_valid():
            schedule_request = form.save()
            create_audit_log(
                request,
                f"Jadval o'zgartirish arizasi yaratildi: {group.name} ({old_day} {old_start_time} -> {schedule_request.new_day} {schedule_request.new_start_time})",
                target_user=request.user,
            )
            messages.success(request, 'Dars jadvalini o‘zgartirish bo‘yicha arizangiz yuborildi.')
            return redirect('users1:teacher_schedule_request_history')

        return render(request, self.template_name, {
            'group': group,
            'old_day': old_day,
            'old_start_time': old_start_time,
            'old_end_time': old_end_time,
            'form': form,
        })


class TeacherScheduleRequestHistoryView(LoginRequiredMixin, TeacherRequiredMixin, TemplateView):
    template_name = 'users1/teacher_schedule_request_history.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        context['requests'] = ScheduleChangeRequest.objects.filter(
            teacher=user
        ).select_related('group', 'reviewed_by').order_by('-submitted_at')
        return context


class ScheduleChangeRequestDetailView(LoginRequiredMixin, DirectorRequiredMixin, TemplateView):
    template_name = 'users1/schedule_change_request_detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        schedule_request = get_object_or_404(
            ScheduleChangeRequest.objects.select_related('group', 'teacher', 'reviewed_by'),
            pk=kwargs.get('request_pk')
        )
        context['schedule_request'] = schedule_request
        return context


@login_required
@require_http_methods(['POST'])
def review_schedule_change_request(request, request_pk):
    if not request.user.is_director:
        raise PermissionDenied
    schedule_request = get_object_or_404(ScheduleChangeRequest, pk=request_pk)
    if schedule_request.status != ScheduleChangeRequest.Status.PENDING:
        messages.error(request, 'Ushbu ariza allaqachon ko‘rib chiqilgan.')
        return redirect('users1:schedule_change_request_detail', request_pk=request_pk)

    decision = request.POST.get('decision')
    comment = request.POST.get('review_comment', '').strip()

    if decision not in ['approve', 'reject']:
        messages.error(request, 'Noto‘g‘ri qaror tanlandi.')
        return redirect('users1:schedule_change_request_detail', request_pk=request_pk)

    if decision == 'reject' and not comment:
        messages.error(request, 'Rad etish uchun izoh kiritish majburiy.')
        return redirect('users1:schedule_change_request_detail', request_pk=request_pk)

    if decision == 'approve':
        schedule_request.status = ScheduleChangeRequest.Status.APPROVED
        schedule_request.effective_week_start = _start_of_week(timezone.localdate())
        schedule_request.save(update_fields=['status', 'effective_week_start'])
        create_audit_log(
            request,
            f"Jadval o'zgartirish arizasi tasdiqlandi: {schedule_request.group.name} ({schedule_request.old_day} {schedule_request.old_start_time}-{schedule_request.old_end_time} → {schedule_request.new_day} {schedule_request.new_start_time}-{schedule_request.new_end_time})",
            target_user=schedule_request.teacher,
        )
        messages.success(request, 'Ariza tasdiqlandi. O‘zgartirish bir hafta davomida qo‘llanadi va keyingi haftadan avvalgiga qaytadi.')
    else:
        schedule_request.status = ScheduleChangeRequest.Status.REJECTED
        create_audit_log(
            request,
            f"Jadval o'zgartirish arizasi rad etildi: {schedule_request.group.name}",
            target_user=schedule_request.teacher,
        )
        messages.success(request, 'Ariza rad etildi.')

    schedule_request.reviewed_by = request.user
    schedule_request.review_comment = comment
    schedule_request.reviewed_at = timezone.now()
    schedule_request.save()

    return redirect('users1:schedule_change_request_detail', request_pk=request_pk)


# ---------------------------------------------------------------------------
# Teacher Groups, Messages, Schedule, Students
# ---------------------------------------------------------------------------
class TeacherGroupsView(LoginRequiredMixin, TeacherRequiredMixin, TemplateView):
    template_name = 'users1/teacher_groups.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        groups = self.request.user.teaching_groups.filter(is_active=True)
        today = timezone.localdate()
        now_time = timezone.localtime().time()
        day_names = ['Dushanba', 'Seshanba', 'Chorshanba', 'Payshanba', 'Juma', 'Shanba', 'Yakshanba']
        today_name = day_names[today.weekday()]

        groups_with_status = []
        for group in groups:
            is_today = False
            if group.lesson_days:
                lesson_days_list = [d.strip() for d in group.lesson_days.split(',') if d.strip()]
                is_today = today_name in lesson_days_list
            groups_with_status.append({
                'group': group,
                'is_today': is_today,
            })

        context['groups_with_status'] = groups_with_status
        context['today'] = today
        return context


class TeacherGroupDetailView(LoginRequiredMixin, TeacherRequiredMixin, TemplateView):
    template_name = 'users1/teacher_group_detail.html'

    def get(self, request, *args, **kwargs):
        group = get_object_or_404(
            Group,
            pk=kwargs.get('pk'),
            teacher=request.user,
            is_active=True,
        )
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        group = get_object_or_404(
            Group,
            pk=self.kwargs.get('pk'),
            teacher=self.request.user,
            is_active=True,
        )
        context['group'] = group

        students = Student.objects.filter(
            groupstudent__group=group,
            groupstudent__is_active=True,
            is_active=True,
        )

        # O'quvchilar va ularning oxirgi davomati
        attendance_qs = AttendanceRecord.objects.filter(
            student__in=students,
            session__group=group,
        ).select_related('session')

        students_with_status = []
        for student in students:
            last_record = attendance_qs.filter(student=student).order_by('-session__date').first()
            students_with_status.append({
                'student': student,
                'last_status': last_record.status if last_record else None,
                'last_date': last_record.session.date if last_record else None,
            })
        context['students_with_status'] = students_with_status
        context['student_count'] = students.count()

        # Dars vaqti hozir yoniqmi?
        is_lesson_active = False
        if group.lesson_time and group.lesson_days:
            day_names = ['Dushanba', 'Seshanba', 'Chorshanba', 'Payshanba', 'Juma', 'Shanba', 'Yakshanba']
            today_name = day_names[timezone.localdate().weekday()]
            lesson_days_list = [d.strip() for d in group.lesson_days.split(',') if d.strip()]

            if today_name in lesson_days_list:
                now_time = timezone.localtime().time()
                import datetime
                if group.end_time:
                    end_time = group.end_time
                else:
                    hours = int(group.duration) if group.duration else 0
                    minutes = int((group.duration - hours) * 60) if group.duration else 0
                    td = datetime.timedelta(hours=hours, minutes=minutes)
                    end_time = (datetime.datetime.combine(datetime.date.today(), group.lesson_time) + td).time()
                is_lesson_active = group.lesson_time <= now_time <= end_time

        context['is_lesson_active'] = is_lesson_active
        return context


class TeacherMessagesView(LoginRequiredMixin, TeacherRequiredMixin, TemplateView):
    template_name = 'users1/teacher_messages.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from bot.models import TelegramAppeal
        context['pending_appeals'] = TelegramAppeal.objects.filter(
            student__groupstudent__group__teacher=self.request.user,
            is_resolved=False
        ).select_related('telegram_user', 'student').order_by('-created_at')
        return context


class TeacherScheduleView(LoginRequiredMixin, TeacherRequiredMixin, TemplateView):
    template_name = 'users1/teacher_schedule.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        groups = self.request.user.teaching_groups.filter(is_active=True).order_by('lesson_time', 'name')
        today = timezone.localdate()
        day_names = ['Dushanba', 'Seshanba', 'Chorshanba', 'Payshanba', 'Juma', 'Shanba', 'Yakshanba']

        week_offset = int(self.request.GET.get('week_offset', 0))
        start_of_week = today - timezone.timedelta(days=today.weekday()) + timezone.timedelta(days=7 * week_offset)
        week_days = []
        for i in range(7):
            check_date = start_of_week + timezone.timedelta(days=i)
            day_name = day_names[check_date.weekday()]
            lessons = []

            for group in groups:
                if not group.lesson_days or not group.lesson_time:
                    continue

                override = _get_week_override(group, start_of_week)
                if override:
                    if day_name == override.new_day:
                        lessons.append({
                            'group': group,
                            'time': override.new_start_time,
                            'room': group.room,
                        })
                    elif day_name == override.old_day:
                        continue
                    else:
                        lesson_days = [d.strip() for d in group.lesson_days.split(',') if d.strip()]
                        if day_name not in lesson_days:
                            continue
                        lessons.append({
                            'group': group,
                            'time': group.lesson_time,
                            'room': group.room,
                        })
                else:
                    lesson_days = [d.strip() for d in group.lesson_days.split(',') if d.strip()]
                    if day_name not in lesson_days:
                        continue

                    lessons.append({
                        'group': group,
                        'time': group.lesson_time,
                        'room': group.room,
                    })

            week_days.append({
                'date': check_date,
                'day_name': day_name,
                'lessons': sorted(lessons, key=lambda item: (item['time'], item['group'].name)),
            })

        context['week_days'] = week_days
        context['week_offset'] = week_offset
        context['week_start'] = start_of_week
        context['week_end'] = start_of_week + timezone.timedelta(days=6)
        context['prev_week_offset'] = week_offset - 1
        context['next_week_offset'] = week_offset + 1
        context['today'] = today
        context['schedule'] = [
            {
                'group': group,
                'time': group.lesson_time,
                'days': group.lesson_days,
            }
            for group in groups
            if group.lesson_days and group.lesson_time
        ]
        return context


class TeacherStudentsView(LoginRequiredMixin, TeacherRequiredMixin, TemplateView):
    template_name = 'users1/teacher_students.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        today = timezone.localdate()

        groups = user.teaching_groups.filter(is_active=True)
        context['groups'] = groups

        students_data = []
        seen_students = set()

        # Optimized TeacherStudentsView
        all_students = Student.objects.filter(
            groupstudent__group__in=groups,
            groupstudent__is_active=True,
            is_active=True
        ).distinct().prefetch_related('groupstudent_set__group')

        # To avoid N+1 for groups list
        # We can also get all active memberships in one go
        memberships_dict = defaultdict(list)
        all_memberships = GroupStudent.objects.filter(
            student__in=all_students,
            is_active=True,
            group__is_active=True
        ).select_related('group')
        for m in all_memberships:
            memberships_dict[m.student_id].append(m.group.name)

        # To avoid N+1 for last attendance
        # We can use a Subquery or just fetch the latest record per student
        # Since we only want the absolute latest for THIS teacher, let's use a trick
        from django.db.models import OuterRef, Subquery
        last_att_subquery = AttendanceRecord.objects.filter(
            student=OuterRef('pk'),
            session__teacher=user
        ).select_related('session').order_by('-session__date')
        
        all_students_with_last_att = all_students.annotate(
            last_record_id=Subquery(last_att_subquery.values('id')[:1]),
        )
        
        # Now fetch the actual records to avoid N+1 again
        record_ids = [s.last_record_id for s in all_students_with_last_att if s.last_record_id]
        records_lookup = {r.student_id: r for r in AttendanceRecord.objects.filter(id__in=record_ids).select_related('session')}

        for student in all_students:
            students_data.append({
                'student': student,
                'groups': memberships_dict[student.pk],
                'last_attendance': records_lookup.get(student.pk),
            })
        
        context['students_data'] = students_data
        return context


class TeacherStudentDetailView(LoginRequiredMixin, TeacherRequiredMixin, TemplateView):
    template_name = 'users1/teacher_student_detail.html'

    def get(self, request, *args, **kwargs):
        student = get_object_or_404(Student, pk=kwargs.get('pk'), is_active=True)
        groups = self.request.user.teaching_groups.filter(is_active=True)
        if not GroupStudent.objects.filter(
            group__in=groups,
            student=student,
            is_active=True,
        ).exists():
            messages.error(request, "Bu o'quvchi sizning guruhlaringizda emas.")
            return redirect('users1:teacher_students')
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        student = get_object_or_404(Student, pk=self.kwargs.get('pk'), is_active=True)
        user = self.request.user

        context['student'] = student
        context['student_groups'] = Group.objects.filter(
            groupstudent__student=student,
            groupstudent__is_active=True,
            is_active=True,
        )

        context['attendance_records'] = AttendanceRecord.objects.filter(
            student=student,
            session__teacher=user,
        ).select_related('session', 'session__group').order_by('-session__date')[:10]

        from bot.models import TelegramUser, TelegramAppeal
        context['telegram_users'] = TelegramUser.objects.filter(
            student=student,
            is_verified=True,
        )

        context['recent_appeals'] = TelegramAppeal.objects.filter(
            student=student,
        ).order_by('-created_at')[:5]

        return context


# ---------------------------------------------------------------------------
# Admin Dashboard (Director)
# ---------------------------------------------------------------------------
class AdminDashboardView(LoginRequiredMixin, DirectorRequiredMixin, TemplateView):
    template_name = 'users1/admin_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        this_month = today.month
        this_year = today.year

        # Asosiy statistika
        context['total_students'] = Student.objects.filter(is_active=True).count()
        context['active_groups_count'] = Group.objects.filter(is_active=True).count()
        context['teachers_count'] = User.objects.filter(role=User.Role.TEACHER, is_deleted=False).count()
        context['admins_count'] = User.objects.filter(role=User.Role.ADMINISTRATOR).count()

        # Qarzdorlar soni
        today = timezone.localdate()
        today_month = first_day_of_month(today)
        context['debtors_count'] = StudentMonthBalance.objects.filter(
            status__in=[MonthBalanceStatus.OPEN, MonthBalanceStatus.PARTIAL],
            month__lte=today_month,
        ).values('student').distinct().count()

        # Bugungi tug'ilgan kunlar
        context['birthdays_today'] = Student.objects.filter(
            birth_date__month=today.month,
            birth_date__day=today.day,
            is_active=True
        )

        # Shu oylik daromad
        context['monthly_income'] = PaymentTransaction.objects.filter(
            payment_date__year=this_year,
            payment_date__month=this_month
        ).aggregate(total=Sum('amount'))['total'] or 0

        # Davomat statistikasi
        context['today_attendance'] = AttendanceRecord.objects.filter(session__date=today).count()

        last_week = today - timezone.timedelta(days=7)
        context['weekly_attendance'] = AttendanceRecord.objects.filter(
            session__date__range=[last_week, today]
        ).count()

        context['monthly_attendance'] = AttendanceRecord.objects.filter(
            session__date__year=this_year,
            session__date__month=this_month
        ).count()

        # Oxirgi to'lovlar
        context['recent_payments'] = PaymentTransaction.objects.select_related('student', 'group').order_by('-created_at')[:5]

        # Oxirgi qo'shilgan o'quvchilar
        context['recent_students'] = Student.objects.filter(is_active=True).order_by('-created_at')[:5]

        # Guruhlar bo'yicha qarzlar
        today = timezone.localdate()
        today_month = first_day_of_month(today)
        debtors_qs = StudentMonthBalance.objects.filter(
            status__in=[MonthBalanceStatus.OPEN, MonthBalanceStatus.PARTIAL],
            month__lte=today_month,
        ).select_related('student', 'group').order_by('group__name', 'month')

        grouped_debtors = defaultdict(lambda: {'group': None, 'students': [], 'total_debt': 0})
        for d in debtors_qs:
            gid = d.group_id
            if grouped_debtors[gid]['group'] is None:
                grouped_debtors[gid]['group'] = d.group
            grouped_debtors[gid]['students'].append(d)
            grouped_debtors[gid]['total_debt'] += float(d.debt_amount)

        sorted_groups_by_debt = sorted(grouped_debtors.values(), key=lambda x: x['total_debt'], reverse=True)
        context['grouped_debtors'] = sorted_groups_by_debt[:5]
        context['worst_group_by_debt'] = sorted_groups_by_debt[0]['group'] if sorted_groups_by_debt else None

        # Ota-onalardan kelgan xabarlar (hal qilinmagan)
        context['pending_appeals'] = TelegramAppeal.objects.filter(
            is_resolved=False
        ).select_related('telegram_user', 'student').order_by('-created_at')[:10]
        context['pending_appeals_count'] = TelegramAppeal.objects.filter(is_resolved=False).count()

        # DAVOMAT olinmagan guruhlar (Optimized)
        from attendance.models import AttendanceSession
        days_map = {
            0: 'Dushanba', 1: 'Seshanba', 2: 'Chorshanba', 3: 'Payshanba',
            4: 'Juma', 5: 'Shanba', 6: 'Yakshanba'
        }
        today_name = days_map[today.weekday()]
        now_time = timezone.localtime().time()

        groups_today = Group.objects.filter(
            is_active=True,
            lesson_days__contains=today_name,
            end_time__lt=now_time
        ).select_related('teacher')

        groups_today_ids = groups_today.values_list('id', flat=True)
        sessions_today_group_ids = set(AttendanceSession.objects.filter(
            group_id__in=groups_today_ids, 
            date=today
        ).values_list('group_id', flat=True))

        missing_attendance = [g for g in groups_today if g.id not in sessions_today_group_ids]
        context['missing_attendance'] = missing_attendance
        context['groups'] = Group.objects.filter(is_active=True).order_by('name')

        # === PENALTY STATISTICS FOR DASHBOARD ===
        context['today_missed_teachers'] = MissedAttendanceAlert.objects.filter(
            lesson_date=today
        ).select_related('teacher', 'group').order_by('-created_at')

        context['pending_alerts'] = MissedAttendanceAlert.objects.filter(
            status=MissedAttendanceAlert.Status.PENDING
        ).select_related('teacher', 'group').order_by('-created_at')
        context['pending_alerts_count'] = context['pending_alerts'].count()

        context['pending_schedule_requests'] = ScheduleChangeRequest.objects.filter(
            status=ScheduleChangeRequest.Status.PENDING
        ).select_related('teacher', 'group').order_by('-submitted_at')[:5]
        context['pending_schedule_requests_count'] = ScheduleChangeRequest.objects.filter(
            status=ScheduleChangeRequest.Status.PENDING
        ).count()

        context['monthly_penalty_total'] = TeacherPenalty.objects.filter(
            created_at__year=this_year,
            created_at__month=this_month,
        ).aggregate(total=Sum('points'))['total'] or 0

        context['recent_penalties'] = TeacherPenalty.objects.select_related('teacher', 'group').order_by('-created_at')[:5]

        # Ketma-ket 3 ta darsda davomat olinmagan teacherlar
        teachers_with_3_consecutive = []
        for teacher in User.objects.filter(role=User.Role.TEACHER, is_deleted=False):
            recent_alerts = MissedAttendanceAlert.objects.filter(
                teacher=teacher,
                status__in=[MissedAttendanceAlert.Status.CAME, MissedAttendanceAlert.Status.NOT_CAME],
                penalty_applied=True,
            ).order_by('-lesson_date')[:3]
            if len(recent_alerts) >= 3:
                teachers_with_3_consecutive.append(teacher)
        context['teachers_with_3_consecutive'] = teachers_with_3_consecutive

        # Botga ulangan/ulnmagan o'quvchilar
        from bot.models import TelegramUser as BotTelegramUser
        all_students = Student.objects.filter(is_active=True)
        bot_connected_ids = BotTelegramUser.objects.filter(
            student__isnull=False,
            is_verified=True,
        ).values_list('student_id', flat=True)
        context['bot_connected_count'] = all_students.filter(pk__in=bot_connected_ids).count()
        context['bot_not_connected_count'] = all_students.exclude(pk__in=bot_connected_ids).count()
        context['blocked_students_count'] = Student.objects.filter(is_active=False).count()

        return context


# ---------------------------------------------------------------------------
# Telegram & Messaging APIs
# ---------------------------------------------------------------------------
@require_http_methods(['POST'])
def send_teacher_message(request):
    """Teacher tomonidan o'quvchining ota-onasiga Telegram xabar yuborish."""
    try:
        payload = json_module.loads(request.body.decode('utf-8'))
    except Exception:
        return JsonResponse({'detail': "Noto'g'ri ma'lumot"}, status=400)

    user = request.user
    if not user.is_authenticated or not user.is_teacher:
        return JsonResponse({'detail': "Faqat o'qituvchi uchun ruxsat bor."}, status=403)

    student_id = payload.get('student_id')
    message_text = payload.get('message', '').strip()

    if not student_id:
        return JsonResponse({'detail': "O'quvchi tanlash kerak."}, status=400)
    if not message_text:
        return JsonResponse({'detail': "Xabar matnini kiriting."}, status=400)

    student = Student.objects.filter(pk=student_id, is_active=True).first()
    if not student:
        return JsonResponse({'detail': "O'quvchi topilmadi."}, status=404)

    groups = user.teaching_groups.filter(is_active=True)
    if not GroupStudent.objects.filter(group__in=groups, student=student, is_active=True).exists():
        return JsonResponse({'detail': "Bu o'quvchi sizning guruhlaringizda emas."}, status=403)

    from bot.models import TelegramUser, TeacherMessage
    from bot.services import send_telegram_message

    telegram_users = TelegramUser.objects.filter(student=student, is_verified=True)

    if not telegram_users.exists():
        return JsonResponse({'detail': "O'quvchining Telegram'dagi ota-onasi topilmadi."}, status=404)

    sent_count = 0
    last_tu = None
    for tu in telegram_users:
        last_tu = tu
        try:
            teacher_name = user.get_full_name() or user.username
            formatted_msg = (
                f"<b>✉️ Xabar o'qituvchidan</b>\n\n"
                f"<b>O'qituvchi:</b> {teacher_name}\n"
                f"<b>O'quvchi:</b> {student}\n\n"
                f"{message_text}"
            )
            send_telegram_message(tu.telegram_id, formatted_msg)
            sent_count += 1
        except Exception:
            pass

    status_val = TeacherMessage.Status.SENT if sent_count > 0 else TeacherMessage.Status.FAILED
    TeacherMessage.objects.create(
        teacher=user,
        student=student,
        parent=last_tu,
        message=message_text,
        status=status_val,
    )

    if sent_count > 0:
        return JsonResponse({'ok': True, 'sent_count': sent_count})
    return JsonResponse({'detail': "Xabar yuborishda xatolik yuz berdi."}, status=500)


@require_http_methods(['POST'])
def reply_appeal(request, appeal_id):
    if not request.user.is_authenticated or not (request.user.is_admin_access or request.user.is_teacher):
        return JsonResponse({'detail': "Ruxsat yo'q."}, status=403)
    appeal = TelegramAppeal.objects.filter(id=appeal_id).first()
    if not appeal:
        return JsonResponse({'detail': 'Xabar topilmadi'}, status=404)

    reply_text = request.POST.get('reply', '').strip()
    if not reply_text:
        return JsonResponse({'detail': 'Javob matni kiriting'}, status=400)

    appeal.is_resolved = True
    appeal.save()

    try:
        from bot.services import send_telegram_message
        if request.user.role == User.Role.TEACHER:
            sender_label = "O'qituvchi"
        else:
            sender_label = "Admin"

        formatted_reply = (
            f"<b>💬 JAVOB KELDI!</b>\n"
            f"──────────────────\n"
            f"👤 <b>Yuboruvchi:</b> {sender_label}\n\n"
            f"Javob: {reply_text}"
        )
        send_telegram_message(appeal.telegram_user.telegram_id, formatted_reply)
    except Exception:
        pass

    messages.success(request, "Javob muvaffaqiyatli yuborildi!")
    return JsonResponse({'ok': True})


@require_http_methods(['POST'])
def resolve_appeal(request, appeal_id):
    if not request.user.is_authenticated or not (request.user.is_admin_access or request.user.is_teacher):
        return JsonResponse({'detail': "Ruxsat yo'q."}, status=403)
    appeal = TelegramAppeal.objects.filter(id=appeal_id).first()
    if not appeal:
        return JsonResponse({'detail': 'Xabar topilmadi'}, status=404)

    appeal.is_resolved = True
    appeal.save()
    messages.success(request, "Xabar hal qilindi deb belgilandi.")
    return JsonResponse({'ok': True})


@require_http_methods(['POST'])
def broadcast_to_group(request):
    if not request.user.is_authenticated or not request.user.is_admin_access:
        return JsonResponse({'detail': "Ruxsat yo'q."}, status=403)
    try:
        payload = json_module.loads(request.body.decode('utf-8'))
    except Exception:
        return JsonResponse({'detail': "Noto'g'ri ma'lumot"}, status=400)

    group_id = payload.get('group_id')
    text = payload.get('message', '').strip()

    if not group_id:
        return JsonResponse({'detail': 'Guruhni tanlang'}, status=400)
    if not text:
        return JsonResponse({'detail': 'Xabar matnini kiriting'}, status=400)

    group = Group.objects.filter(pk=group_id, is_active=True).first()
    if not group:
        return JsonResponse({'detail': 'Guruh topilmadi'}, status=404)

    students = Student.objects.filter(
        groupstudent__group=group,
        groupstudent__is_active=True,
        is_active=True,
    )

    sender = request.user
    if sender.is_director:
        sender_label = "Director"
    elif sender.is_administrator_role:
        sender_label = "Admin"
    else:
        sender_label = "O'qituvchi"
    formatted_msg = f"<b>✉️ {sender_label} xabari</b>\n\n{text}"

    sent_count = 0
    for student in students:
        telegram_users = TelegramUser.objects.filter(student=student, is_verified=True).exclude(
            user__role__in=[User.Role.DIRECTOR, User.Role.ADMINISTRATOR, User.Role.TEACHER]
        )
        for tu in telegram_users:
            try:
                from bot.services import send_telegram_message
                send_telegram_message(tu.telegram_id, formatted_msg)
                sent_count += 1
            except Exception:
                pass

    return JsonResponse({'ok': True, 'sent_count': sent_count, 'group_name': group.name})


@require_http_methods(['POST'])
def broadcast_all(request):
    if not request.user.is_authenticated or not request.user.is_director:
        return JsonResponse({'detail': "Faqat Director uchun ruxsat bor."}, status=403)
    try:
        payload = json_module.loads(request.body.decode('utf-8'))
    except Exception:
        return JsonResponse({'detail': "Noto'g'ri ma'lumot"}, status=400)

    text = payload.get('message', '').strip()
    if not text:
        return JsonResponse({'detail': 'Xabar matnini kiriting'}, status=400)

    sender = request.user
    if sender.is_director:
        sender_label = "Director"
    elif sender.is_administrator_role:
        sender_label = "Admin"
    else:
        sender_label = "O'qituvchi"
    formatted_msg = f"<b>✉️ {sender_label} xabari</b>\n\n{text}"

    telegram_users = TelegramUser.objects.filter(is_verified=True).exclude(
        user__role__in=[User.Role.DIRECTOR, User.Role.ADMINISTRATOR, User.Role.TEACHER]
    )

    sent_count = 0
    for tu in telegram_users:
        try:
            from bot.services import send_telegram_message
            send_telegram_message(tu.telegram_id, formatted_msg)
            sent_count += 1
        except Exception:
            pass

    return JsonResponse({'ok': True, 'sent_count': sent_count})


# ---------------------------------------------------------------------------
# Bot holati sahifasi
# ---------------------------------------------------------------------------
class BotStatusView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    def test_func(self):
        return self.request.user.is_authenticated and (
            self.request.user.is_director or self.request.user.is_administrator_role
        )

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return redirect('users1:login')
        return redirect('users1:teacher_dashboard')

    template_name = 'users1/bot_status.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        status = self.request.GET.get('status', 'connected')

        from bot.models import TelegramUser as BotTelegramUser
        all_students = Student.objects.filter(is_active=True)
        blocked_students = Student.objects.filter(is_active=False)

        bot_connected_ids = list(BotTelegramUser.objects.filter(
            student__isnull=False,
            is_verified=True,
        ).values_list('student_id', flat=True))

        if status == 'connected':
            students = all_students.filter(pk__in=bot_connected_ids).order_by('last_name', 'first_name')
            title = "Botga ulangan o'quvchilar"
        elif status == 'not_connected':
            students = all_students.exclude(pk__in=bot_connected_ids).order_by('last_name', 'first_name')
            title = "Botga ulanmagan o'quvchilar"
        elif status == 'blocked':
            students = blocked_students.order_by('last_name', 'first_name')
            title = "Bloklangan/o'chirilgan o'quvchilar"
        else:
            students = all_students.order_by('last_name', 'first_name')
            title = "Barcha o'quvchilar"

        context['students'] = students
        context['title'] = title
        context['current_status'] = status
        context['connected_count'] = all_students.filter(pk__in=bot_connected_ids).count()
        context['not_connected_count'] = all_students.exclude(pk__in=bot_connected_ids).count()
        context['blocked_count'] = blocked_students.count()

        return context


# ---------------------------------------------------------------------------
# Administrator Dashboard
# ---------------------------------------------------------------------------
class AdministratorDashboardView(LoginRequiredMixin, AdministratorRequiredMixin, TemplateView):
    template_name = 'users1/administrator_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()

        context['active_groups_count'] = Group.objects.filter(is_active=True).count()
        context['total_students_count'] = Student.objects.filter(is_active=True).count()

        context['today_attendance'] = AttendanceRecord.objects.filter(
            session__date=today
        ).count()

        context['my_payments'] = PaymentTransaction.objects.filter(
            created_by=self.request.user
        ).select_related('student', 'group').order_by('-created_at')[:10]

        context['groups'] = Group.objects.filter(is_active=True).order_by('name')

        # DAVOMAT olinmagan guruhlar (Optimized)
        from attendance.models import AttendanceSession
        days_map = {
            0: 'Dushanba', 1: 'Seshanba', 2: 'Chorshanba', 3: 'Payshanba',
            4: 'Juma', 5: 'Shanba', 6: 'Yakshanba'
        }
        today_name = days_map[today.weekday()]
        now_time = timezone.localtime().time()

        groups_today = Group.objects.filter(
            is_active=True,
            lesson_days__contains=today_name,
            end_time__lt=now_time
        ).select_related('teacher')

        groups_today_ids = groups_today.values_list('id', flat=True)
        sessions_today_group_ids = set(AttendanceSession.objects.filter(
            group_id__in=groups_today_ids, 
            date=today
        ).values_list('group_id', flat=True))

        missing_attendance = [g for g in groups_today if g.id not in sessions_today_group_ids]
        context['missing_attendance'] = missing_attendance

        # Pending alerts for administrator notification
        context['pending_alerts'] = MissedAttendanceAlert.objects.filter(
            status=MissedAttendanceAlert.Status.PENDING
        ).select_related('teacher', 'group').order_by('-created_at')[:10]
        context['pending_alerts_count'] = MissedAttendanceAlert.objects.filter(
            status=MissedAttendanceAlert.Status.PENDING
        ).count()

        context['pending_schedule_requests'] = ScheduleChangeRequest.objects.filter(
            status=ScheduleChangeRequest.Status.PENDING
        ).select_related('teacher', 'group').order_by('-submitted_at')[:5]
        context['pending_schedule_requests_count'] = ScheduleChangeRequest.objects.filter(
            status=ScheduleChangeRequest.Status.PENDING
        ).count()

        # Botga ulangan/ulnmagan o'quvchilar
        from bot.models import TelegramUser as BotTelegramUser
        all_students = Student.objects.filter(is_active=True)
        bot_connected_ids = BotTelegramUser.objects.filter(
            student__isnull=False,
            is_verified=True,
        ).values_list('student_id', flat=True)
        context['bot_connected_count'] = all_students.filter(pk__in=bot_connected_ids).count()
        context['bot_not_connected_count'] = all_students.exclude(pk__in=bot_connected_ids).count()
        context['blocked_students_count'] = Student.objects.filter(is_active=False).count()

        return context
