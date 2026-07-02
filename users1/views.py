import json as json_module
import os

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.views import LoginView
from django.contrib.auth import update_session_auth_hash
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, get_object_or_404, render
from django.views.generic import TemplateView, ListView, CreateView, UpdateView
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from django.urls import reverse_lazy
from django import forms
from django.db.models import Sum, Count, Q
from django.utils import timezone

from students.models import Student
from payments.models import StudentMonthBalance, MonthBalanceStatus, PaymentTransaction
from attendance.models import AttendanceRecord, AttendanceSession
from groups_app.models import Group, GroupStudent
from bot.models import TelegramAppeal, TelegramUser
from .models import User, AuditLog, TeacherPenalty, MissedAttendanceAlert


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
        return User.objects.filter(role='TEACHER').order_by('last_name', 'first_name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['total_teachers'] = User.objects.filter(role='TEACHER').count()
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


@require_http_methods(['POST'])
def director_toggle_teacher_block(request, pk):
    """Director teacher akkauntini bloklaydi/faollashtiradi"""
    if not request.user.is_authenticated or not request.user.is_director:
        return JsonResponse({'error': 'Ruxsat yo\'q'}, status=403)

    teacher = get_object_or_404(User, pk=pk, role=User.Role.TEACHER)
    teacher.is_blocked = not teacher.is_blocked
    teacher.save()

    action = "bloklandi" if teacher.is_blocked else "faollashtirildi"
    create_audit_log(request, f"O'qituvchi akkaunti {action}: {teacher.username}", target_user=teacher)
    return JsonResponse({
        'ok': True,
        'is_blocked': teacher.is_blocked,
        'message': f"Akkount {action}"
    })


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
        context['teachers'] = User.objects.filter(role=User.Role.TEACHER)

        # Teacher-based stats
        teacher_stats = []
        for teacher in User.objects.filter(role=User.Role.TEACHER):
            total = TeacherPenalty.objects.filter(teacher=teacher).aggregate(
                total=Sum('points')
            )['total'] or 0
            monthly = TeacherPenalty.objects.filter(
                teacher=teacher,
                created_at__year=this_year,
                created_at__month=this_month,
            ).aggregate(total=Sum('points'))['total'] or 0
            teacher_stats.append({
                'teacher': teacher,
                'total_points': total,
                'monthly_points': monthly,
            })
        teacher_stats.sort(key=lambda x: x['total_points'])
        context['teacher_stats'] = teacher_stats

        context['monthly_total'] = TeacherPenalty.objects.filter(
            created_at__year=this_year,
            created_at__month=this_month,
        ).aggregate(total=Sum('points'))['total'] or 0

        context['missed_alerts'] = MissedAttendanceAlert.objects.filter(
            status=MissedAttendanceAlert.Status.PENDING
        ).select_related('teacher', 'group').order_by('-created_at')[:20]

        # Ketma-ket 3 ta darsda davomat olinmagan teacherlar
        teachers_with_3_consecutive = []
        for teacher in User.objects.filter(role=User.Role.TEACHER):
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

        # Penalty info
        context['total_penalty_points'] = TeacherPenalty.objects.filter(teacher=user).aggregate(
            total=Sum('points')
        )['total'] or 0

        return context


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
        groups = self.request.user.teaching_groups.filter(is_active=True)
        today = timezone.localdate()

        schedule = []
        for group in groups:
            if group.lesson_days and group.lesson_time:
                from attendance.models import LessonPlan, AttendanceSession
                upcoming_dates = []
                for i in range(7):
                    check_date = today + timezone.timedelta(days=i)
                    day_names = ['Dushanba', 'Seshanba', 'Chorshanba', 'Payshanba', 'Juma', 'Shanba', 'Yakshanba']
                    if day_names[check_date.weekday()] in group.lesson_days:
                        plan = LessonPlan.objects.filter(group=group, date=check_date).first()
                        session = AttendanceSession.objects.filter(group=group, date=check_date).first()
                        upcoming_dates.append({
                            'date': check_date,
                            'day_name': day_names[check_date.weekday()],
                            'topic': plan.topic if plan else (session.lesson_topic if session and session.lesson_topic else ''),
                            'has_plan': bool(plan),
                            'has_session': bool(session),
                        })

                schedule.append({
                    'group': group,
                    'time': group.lesson_time,
                    'days': group.lesson_days,
                    'upcoming_dates': upcoming_dates,
                })
        context['schedule'] = schedule
        context['today'] = today
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

        for group in groups:
            memberships = GroupStudent.objects.filter(
                group=group,
                is_active=True,
                student__is_active=True,
            ).select_related('student')

            for membership in memberships:
                student = membership.student
                if student.pk in seen_students:
                    continue
                seen_students.add(student.pk)

                last_attendance = AttendanceRecord.objects.filter(
                    student=student,
                    session__teacher=user,
                ).select_related('session').order_by('-session__date').first()

                student_groups = Group.objects.filter(
                    groupstudent__student=student,
                    groupstudent__is_active=True,
                    is_active=True,
                ).values_list('name', flat=True)

                students_data.append({
                    'student': student,
                    'groups': list(student_groups),
                    'last_attendance': last_attendance,
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
        context['teachers_count'] = User.objects.filter(role=User.Role.TEACHER).count()
        context['admins_count'] = User.objects.filter(role=User.Role.ADMINISTRATOR).count()

        # Qarzdorlar soni
        context['debtors_count'] = StudentMonthBalance.objects.filter(
            status__in=[MonthBalanceStatus.OPEN, MonthBalanceStatus.PARTIAL]
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
        from collections import defaultdict
        debtors_qs = StudentMonthBalance.objects.filter(
            status__in=[MonthBalanceStatus.OPEN, MonthBalanceStatus.PARTIAL]
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

        # DAVOMAT olinmagan guruhlar
        missing_attendance = []
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

        for group in groups_today:
            if not AttendanceSession.objects.filter(group=group, date=today).exists():
                missing_attendance.append(group)

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

        context['monthly_penalty_total'] = TeacherPenalty.objects.filter(
            created_at__year=this_year,
            created_at__month=this_month,
        ).aggregate(total=Sum('points'))['total'] or 0

        context['recent_penalties'] = TeacherPenalty.objects.select_related('teacher', 'group').order_by('-created_at')[:5]

        # Ketma-ket 3 ta darsda davomat olinmagan teacherlar
        teachers_with_3_consecutive = []
        for teacher in User.objects.filter(role=User.Role.TEACHER):
            recent_alerts = MissedAttendanceAlert.objects.filter(
                teacher=teacher,
                status__in=[MissedAttendanceAlert.Status.CAME, MissedAttendanceAlert.Status.NOT_CAME],
                penalty_applied=True,
            ).order_by('-lesson_date')[:3]
            if len(recent_alerts) >= 3:
                teachers_with_3_consecutive.append(teacher)
        context['teachers_with_3_consecutive'] = teachers_with_3_consecutive

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
        send_telegram_message(appeal.telegram_user.telegram_id, reply_text)
    except Exception:
        pass

    messages.success(request, "Javob muvaffaqiyatli yuborildi!")
    return JsonResponse({'ok': True})


@require_http_methods(['POST'])
def resolve_appeal(request, appeal_id):
    appeal = TelegramAppeal.objects.filter(id=appeal_id).first()
    if not appeal:
        return JsonResponse({'detail': 'Xabar topilmadi'}, status=404)

    appeal.is_resolved = True
    appeal.save()
    messages.success(request, "Xabar hal qilindi deb belgilandi.")
    return JsonResponse({'ok': True})


@require_http_methods(['POST'])
def broadcast_to_group(request):
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

    sent_count = 0
    for student in students:
        telegram_users = TelegramUser.objects.filter(student=student, is_verified=True)
        for tu in telegram_users:
            try:
                from bot.services import send_telegram_message
                send_telegram_message(tu.telegram_id, text)
                sent_count += 1
            except Exception:
                pass

    return JsonResponse({'ok': True, 'sent_count': sent_count, 'group_name': group.name})


@require_http_methods(['POST'])
def broadcast_all(request):
    try:
        payload = json_module.loads(request.body.decode('utf-8'))
    except Exception:
        return JsonResponse({'detail': "Noto'g'ri ma'lumot"}, status=400)

    text = payload.get('message', '').strip()
    if not text:
        return JsonResponse({'detail': 'Xabar matnini kiriting'}, status=400)

    telegram_users = TelegramUser.objects.filter(is_verified=True)

    sent_count = 0
    for tu in telegram_users:
        try:
            from bot.services import send_telegram_message
            send_telegram_message(tu.telegram_id, text)
            sent_count += 1
        except Exception:
            pass

    return JsonResponse({'ok': True, 'sent_count': sent_count})


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

        missing_attendance = []
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

        for group in groups_today:
            if not AttendanceSession.objects.filter(group=group, date=today).exists():
                missing_attendance.append(group)

        context['missing_attendance'] = missing_attendance

        # Pending alerts for administrator notification
        context['pending_alerts'] = MissedAttendanceAlert.objects.filter(
            status=MissedAttendanceAlert.Status.PENDING
        ).select_related('teacher', 'group').order_by('-created_at')[:10]
        context['pending_alerts_count'] = MissedAttendanceAlert.objects.filter(
            status=MissedAttendanceAlert.Status.PENDING
        ).count()

        return context
