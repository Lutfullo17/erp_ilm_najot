from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.views import LoginView
from django.http import HttpResponse
from django.shortcuts import redirect
from django.views.generic import TemplateView, ListView


from django.utils import timezone
from django.db.models import Sum
from students.models import Student
from payments.models import StudentMonthBalance, MonthBalanceStatus, PaymentTransaction
from attendance.models import AttendanceRecord

def index(request):
    if request.user.is_authenticated:
        if request.user.is_admin_role:
            return redirect('users1:admin_dashboard')
        if request.user.is_teacher:
            return redirect('users1:teacher_dashboard')
    return redirect('users1:login')


class RoleLoginView(LoginView):
    template_name = 'users1/login.html'
    redirect_authenticated_user = True

    def get_success_url(self):
        user = self.request.user
        if user.is_admin_role:
            return '/users/admin/'
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


class AdminRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.is_admin_role

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return redirect('users1:login')
        return redirect('users1:teacher_dashboard')


class TeacherDashboardView(LoginRequiredMixin, TeacherRequiredMixin, ListView):
    template_name = 'users1/teacher_dashboard.html'
    context_object_name = 'groups'

    def get_queryset(self):
        return self.request.user.teaching_groups.filter(is_active=True)


class AdminDashboardView(LoginRequiredMixin, AdminRequiredMixin, TemplateView):
    template_name = 'users1/admin_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        
        # Jami o'quvchilar
        context['total_students'] = Student.objects.filter(is_active=True).count()
        
        # Qarzdorlar soni
        context['debtors_count'] = StudentMonthBalance.objects.filter(
            status__in=[MonthBalanceStatus.OPEN, MonthBalanceStatus.PARTIAL]
        ).values('student').distinct().count()
        
        # Shu oylik daromad
        context['monthly_income'] = PaymentTransaction.objects.filter(
            payment_date__year=today.year,
            payment_date__month=today.month
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        # Bugungi davomat (Kelgan o'quvchilar soni)
        context['today_attendance'] = AttendanceRecord.objects.filter(
            session__date=today
        ).count()
        
        return context
