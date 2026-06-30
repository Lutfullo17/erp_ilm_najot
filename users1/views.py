from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.views import LoginView
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, get_object_or_404
from django.views.generic import TemplateView, ListView, CreateView, UpdateView
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from django.urls import reverse_lazy
from django import forms

from django.utils import timezone
from django.db.models import Sum
from students.models import Student
from payments.models import StudentMonthBalance, MonthBalanceStatus, PaymentTransaction
from attendance.models import AttendanceRecord, AttendanceSession
from groups_app.models import Group, GroupStudent
from bot.models import TelegramAppeal, TelegramUser
from .models import User


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


def index(request):
    if request.user.is_authenticated:
        if request.user.is_director:
            return redirect('users1:admin_dashboard')
        if request.user.is_administrator_role:
            return redirect('users1:administrator_dashboard')
        if request.user.is_teacher:
            return redirect('users1:teacher_dashboard')
    return redirect('users1:login')


class RoleLoginView(LoginView):
    template_name = 'users1/login.html'
    redirect_authenticated_user = True

    def get_success_url(self):
        user = self.request.user
        if user.is_director:
            return '/users/admin/'
        if user.is_administrator_role:
            return '/users/administrator/'
        if user.is_teacher:
            return '/users/teacher/'
        return '/users/'


class TeacherRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.is_teacher

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
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
        return self.request.user.is_authenticated and self.request.user.is_administrator_role

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return redirect('users1:login')
        if self.request.user.is_director:
            return redirect('users1:admin_dashboard')
        return redirect('users1:teacher_dashboard')


class AdminAccessRequiredMixin(UserPassesTestMixin):
    """Access for either Director or Administrator"""
    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.is_admin_access

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return redirect('users1:login')
        return redirect('users1:teacher_dashboard')


class TeacherDashboardView(LoginRequiredMixin, TeacherRequiredMixin, TemplateView):
    template_name = 'users1/teacher_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        today = timezone.localdate()
        weekday = today.weekday()

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
        for group in groups:
            if group.lesson_days and group.lesson_time:
                lesson_data = {'group': group, 'time': group.lesson_time, 'days': group.lesson_days}
                if today_name in group.lesson_days:
                    today_lessons.append(lesson_data)
                else:
                    upcoming_lessons.append(lesson_data)

        context['today_lessons'] = today_lessons
        context['upcoming_lessons'] = upcoming_lessons[:5]

        return context


class TeacherGroupsView(LoginRequiredMixin, TeacherRequiredMixin, TemplateView):
    template_name = 'users1/teacher_groups.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['groups'] = self.request.user.teaching_groups.filter(is_active=True)
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
                # Kelgusi 7 kun uchun mavzular
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


class TeacherProfileView(LoginRequiredMixin, TeacherRequiredMixin, TemplateView):
    template_name = 'users1/teacher_profile.html'


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
        
        # Haftalik davomat (oxirgi 7 kun)
        last_week = today - timezone.timedelta(days=7)
        context['weekly_attendance'] = AttendanceRecord.objects.filter(
            session__date__range=[last_week, today]
        ).count()

        # Oylik davomat
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

        # OTVAR: Davomat olinmagan guruhlar
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
            # Bugun uchun davomat sessiyasi bormi?
            if not AttendanceSession.objects.filter(group=group, date=today).exists():
                missing_attendance.append(group)
        
        context['missing_attendance'] = missing_attendance
        # Guruhlar ro'yxati (xabar yuborish uchun)
        context['groups'] = Group.objects.filter(is_active=True).order_by('name')

        return context


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

    # Telegram orqali javob yuborish
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
    import json
    try:
        payload = json.loads(request.body.decode('utf-8'))
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
    import json
    try:
        payload = json.loads(request.body.decode('utf-8'))
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


class AdministratorDashboardView(LoginRequiredMixin, AdministratorRequiredMixin, TemplateView):
    template_name = 'users1/administrator_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()

        # Faol guruhlar
        context['active_groups_count'] = Group.objects.filter(is_active=True).count()
        
        # Jami o'quvchilar
        context['total_students_count'] = Student.objects.filter(is_active=True).count()

        # Bugungi davomat
        context['today_attendance'] = AttendanceRecord.objects.filter(
            session__date=today
        ).count()

        # Faqat o'zi qilgan to'lovlar tarixim (oxirgi 10 tasi)
        context['my_payments'] = PaymentTransaction.objects.filter(
            created_by=self.request.user
        ).select_related('student', 'group').order_by('-created_at')[:10]

        # Guruhlar ro'yxati
        context['groups'] = Group.objects.filter(is_active=True).order_by('name')

        # OTVAR: Davomat olinmagan guruhlar
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

        return context


class TeacherListView(LoginRequiredMixin, DirectorRequiredMixin, ListView):
    template_name = 'users1/teacher_list.html'
    context_object_name = 'teachers'

    def get_queryset(self):
        from .models import User
        return User.objects.filter(role='TEACHER').order_by('last_name', 'first_name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from .models import User
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
        messages.success(self.request, "O'qituvchi ma'lumotlari yangilandi!")
        return redirect('users1:teacher_list')


@require_http_methods(['POST'])
def delete_teacher(request, pk):
    teacher = get_object_or_404(User, pk=pk, role='TEACHER')
    teacher.delete()
    messages.success(request, f"{teacher.get_full_name()} o'chirildi.")
    return redirect('users1:teacher_list')
