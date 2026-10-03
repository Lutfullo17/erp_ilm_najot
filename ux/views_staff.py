from django import forms
from django.contrib import messages
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

from groups_app.models import Group
from users1.models import AuditLog, MissedAttendanceAlert, TeacherPenalty, User
from users1.views import delete_teacher as old_delete_teacher

from .base import UxView, ux_login
from .forms import normalize_phone

DIRECTOR = {'director'}


class PersonForm(forms.Form):
    full_name = forms.CharField(max_length=300, error_messages={'required': "Ism va familiyani kiriting. Masalan: Aziza Qodirova"})
    username = forms.CharField(max_length=150, error_messages={'required': "Login kiriting. Masalan: aziza.q"})
    phone = forms.CharField(required=False)
    password1 = forms.CharField(required=False, widget=forms.PasswordInput)
    password2 = forms.CharField(required=False, widget=forms.PasswordInput)

    def __init__(self, *args, instance=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance = instance

    def clean_full_name(self):
        name = ' '.join(self.cleaned_data['full_name'].split())
        if len(name.split()) < 1 or len(name) < 2:
            raise forms.ValidationError("Ism va familiyani kiriting. Masalan: Aziza Qodirova")
        return name

    def clean_username(self):
        u = self.cleaned_data['username'].strip()
        if not all(ch.isalnum() or ch in '@.+-_' for ch in u):
            raise forms.ValidationError("Login faqat harf, raqam va . - _ belgilaridan iborat bo'lsin.")
        qs = User.objects.filter(username__iexact=u)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("Bu login band. Boshqa login tanlang.")
        return u

    def clean_phone(self):
        return normalize_phone(self.cleaned_data.get('phone'))

    def clean(self):
        data = super().clean()
        p1, p2 = data.get('password1'), data.get('password2')
        if not self.instance or p1 or p2:
            if not p1:
                self.add_error('password1', "Parol kiriting (kamida 8 belgi).")
            elif p1 != p2:
                self.add_error('password2', "Parollar mos kelmadi.")
            else:
                try:
                    validate_password(p1, user=self.instance or User(username=data.get('username', ''), first_name=data.get('full_name', '')))
                except ValidationError as exc:
                    self.add_error('password1', ' '.join(exc.messages))
        return data


def _split(name):
    parts = name.split(None, 1)
    return parts[0], (parts[1] if len(parts) > 1 else '')


class StaffView(UxView):
    roles = DIRECTOR
    template_name = 'new/staff.html'

    def get(self, request):
        tab = request.GET.get('tab', 'teachers')
        today = timezone.localdate()
        ctx = {'tab': tab}
        if tab == 'admins':
            ctx['admins'] = User.objects.filter(role=User.Role.ADMINISTRATOR).order_by('last_name', 'first_name')
        elif tab == 'penalties':
            ctx['alerts'] = MissedAttendanceAlert.objects.filter(status=MissedAttendanceAlert.Status.PENDING).select_related('teacher', 'group')[:30]
            ctx['recent'] = TeacherPenalty.objects.select_related('teacher', 'group').order_by('-created_at')[:30]
        else:
            ctx['teachers'] = User.objects.filter(role='TEACHER', is_deleted=False).annotate(
                n_groups=Count('teaching_groups', filter=Q(teaching_groups__is_active=True), distinct=True),
                month_points=Sum('penalties__points', filter=Q(penalties__created_at__year=today.year, penalties__created_at__month=today.month)),
            ).order_by('last_name', 'first_name')
        ctx['pending_alerts'] = MissedAttendanceAlert.objects.filter(status=MissedAttendanceAlert.Status.PENDING).count()
        return self.render(request, ctx)


class TeacherNewView(UxView):
    roles = DIRECTOR
    template_name = 'new/person_form.html'

    def get(self, request):
        return self.render(request, {'form': PersonForm(), 'kind': 'teacher', 'edit': False})

    def post(self, request):
        form = PersonForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Ba'zi maydonlar noto'g'ri. Qizil yozuvlarni tuzating.")
            return self.render(request, {'form': form, 'kind': 'teacher', 'edit': False}, status=400)
        d = form.cleaned_data
        first, last = _split(d['full_name'])
        user = User(username=d['username'], first_name=first, last_name=last, phone=d['phone'], role=User.Role.TEACHER)
        user.set_password(d['password1'])
        user.save()
        AuditLog.objects.create(user=request.user, role=request.user.role, target_user=user, action=f"O'qituvchi yaratildi: {user.username}")
        messages.success(request, f"{user.get_full_name()} o'qituvchi sifatida qo'shildi.")
        return redirect('new:staff_teacher', pk=user.pk)


class AdminNewView(TeacherNewView):
    def get(self, request):
        return self.render(request, {'form': PersonForm(), 'kind': 'admin', 'edit': False})

    def post(self, request):
        form = PersonForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Ba'zi maydonlar noto'g'ri. Qizil yozuvlarni tuzating.")
            return self.render(request, {'form': form, 'kind': 'admin', 'edit': False}, status=400)
        d = form.cleaned_data
        first, last = _split(d['full_name'])
        user = User(username=d['username'], first_name=first, last_name=last, phone=d['phone'], role=User.Role.ADMINISTRATOR)
        user.set_password(d['password1'])
        user.save()
        AuditLog.objects.create(user=request.user, role=request.user.role, target_user=user, action=f"Administrator yaratildi: {user.username}")
        messages.success(request, f"{user.get_full_name()} administrator sifatida qo'shildi.")
        return redirect('/new/staff/?tab=admins')


class TeacherEditView(UxView):
    roles = DIRECTOR
    template_name = 'new/person_form.html'

    def _obj(self, pk):
        return get_object_or_404(User, pk=pk, role='TEACHER', is_deleted=False)

    def get(self, request, pk):
        t = self._obj(pk)
        form = PersonForm(instance=t, initial={'full_name': t.get_full_name(), 'username': t.username, 'phone': t.phone})
        return self.render(request, {'form': form, 'kind': 'teacher', 'edit': True, 'obj': t})

    def post(self, request, pk):
        t = self._obj(pk)
        form = PersonForm(request.POST, instance=t)
        if not form.is_valid():
            messages.error(request, "Ba'zi maydonlar noto'g'ri. Qizil yozuvlarni tuzating.")
            return self.render(request, {'form': form, 'kind': 'teacher', 'edit': True, 'obj': t}, status=400)
        d = form.cleaned_data
        t.first_name, t.last_name = _split(d['full_name'])
        t.username, t.phone = d['username'], d['phone']
        if d.get('password1'):
            t.set_password(d['password1'])
        t.save()
        AuditLog.objects.create(user=request.user, role=request.user.role, target_user=t, action=f"O'qituvchi ma'lumotlari yangilandi: {t.username}")
        messages.success(request, "O'zgarishlar saqlandi.")
        return redirect('new:staff_teacher', pk=t.pk)


class TeacherDetailNewView(UxView):
    roles = DIRECTOR
    template_name = 'new/teacher_detail.html'

    def get(self, request, pk):
        t = get_object_or_404(User, pk=pk, role='TEACHER', is_deleted=False)
        total = TeacherPenalty.objects.filter(teacher=t).aggregate(s=Sum('points'))['s'] or 0
        return self.render(request, {
            'obj': t, 'groups': Group.objects.filter(teacher=t, is_active=True),
            'penalties': TeacherPenalty.objects.filter(teacher=t).select_related('group').order_by('-created_at')[:30],
            'total_points': total,
            'logs': AuditLog.objects.filter(target_user=t).order_by('-created_at')[:15],
        })


@require_POST
@ux_login(DIRECTOR)
def teacher_delete(request, pk):
    old_delete_teacher(request, pk)
    return redirect('new:staff')
