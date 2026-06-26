import json
from datetime import date
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import models
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from users1.views import AdminRequiredMixin
from .models import PaymentTransaction, StudentMonthBalance
from students.models import Student
from groups_app.models import Group, GroupStudent
from .services import PaymentInputError, apply_payment, get_student_payment_state


@require_http_methods(['GET'])
def api_search_students(request):
    query = request.GET.get('q', '').strip()
    if len(query) < 2:
        return JsonResponse({'students': []})

    students = Student.objects.filter(
        models.Q(first_name__icontains=query) |
        models.Q(last_name__icontains=query) |
        models.Q(phone__icontains=query),
        is_active=True,
    ).distinct()[:20]

    results = []
    for student in students:
        groups = GroupStudent.objects.filter(
            student=student,
            is_active=True,
            group__is_active=True,
        ).select_related('group').values(
            'group__id', 'group__name', 'group__monthly_fee'
        )
        results.append({
            'id': student.id,
            'full_name': f'{student.first_name} {student.last_name}',
            'phone': student.phone,
            'groups': [
                {
                    'id': g['group__id'],
                    'name': g['group__name'],
                    'monthly_fee': str(g['group__monthly_fee']),
                }
                for g in groups
            ],
        })

    return JsonResponse({'students': results})

class PaymentListView(LoginRequiredMixin, AdminRequiredMixin, ListView):
    model = PaymentTransaction
    template_name = 'payments/payment_list.html'
    context_object_name = 'payments'
    paginate_by = 20

    def get_queryset(self):
        return PaymentTransaction.objects.all().order_by('-payment_date', '-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from django.utils import timezone
        from django.db.models import Sum
        today = timezone.localdate()
        context['monthly_income'] = PaymentTransaction.objects.filter(
            payment_date__year=today.year,
            payment_date__month=today.month
        ).aggregate(total=Sum('amount'))['total'] or 0
        return context

class PaymentCreateView(LoginRequiredMixin, AdminRequiredMixin, CreateView):
    model = PaymentTransaction
    template_name = 'payments/payment_form.html'
    fields = ['student', 'group', 'amount', 'payment_date', 'method', 'note']
    success_url = reverse_lazy('payments:payment_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['groups'] = Group.objects.filter(is_active=True).order_by('name')
        context['today'] = date.today().isoformat()
        return context

    def form_valid(self, form):
        try:
            apply_payment(
                self.request.user,
                self.request.POST.get('student'),
                self.request.POST.get('group'),
                self.request.POST.get('amount'),
                self.request.POST.get('payment_date'),
                self.request.POST.get('method'),
                self.request.POST.get('note'),
            )
            return redirect(self.success_url)
        except Exception as e:
            form.add_error(None, str(e))
            return self.form_invalid(form)

class DebtorListView(LoginRequiredMixin, AdminRequiredMixin, ListView):
    model = StudentMonthBalance
    template_name = 'payments/debtor_list.html'
    context_object_name = 'debtors'

    def get_queryset(self):
        return StudentMonthBalance.objects.filter(
            status__in=['OPEN', 'PARTIAL']
        ).select_related('student', 'group')


class GroupDebtorView(LoginRequiredMixin, AdminRequiredMixin, ListView):
    model = StudentMonthBalance
    template_name = 'payments/group_debtor_list.html'
    context_object_name = 'debtors'

    def get_queryset(self):
        self.group = get_object_or_404(Group, pk=self.kwargs['group_id'])
        return StudentMonthBalance.objects.filter(
            group=self.group,
            status__in=['OPEN', 'PARTIAL']
        ).select_related('student').order_by('student__last_name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['group'] = self.group
        total = sum(d.debt_amount for d in context['debtors'])
        context['total_debt'] = total
        return context

@require_http_methods(['GET'])
def student_balance(request, student_id, group_id):
    try:
        months = int(request.GET.get('months', 6))
        months = max(1, min(months, 24))
        data = get_student_payment_state(
            student_id,
            group_id,
            request.GET.get('from_month'),
            months,
        )
        return JsonResponse(data)
    except Exception as e:
        return JsonResponse({'detail': str(e)}, status=400)

@require_http_methods(['POST'])
def create_payment(request):
    try:
        payload = json.loads(request.body.decode('utf-8'))
        data = apply_payment(
            request.user,
            payload.get('student_id'),
            payload.get('group_id'),
            payload.get('amount'),
            payload.get('payment_date'),
            payload.get('method', 'CASH'),
            payload.get('note', ''),
        )
        return JsonResponse(data, status=201)
    except Exception as e:
        return JsonResponse({'detail': str(e)}, status=400)
