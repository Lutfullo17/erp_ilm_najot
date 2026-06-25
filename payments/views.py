import json
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
from groups_app.models import Group
from .services import PaymentInputError, apply_payment, get_student_payment_state

class PaymentListView(LoginRequiredMixin, AdminRequiredMixin, ListView):
    model = PaymentTransaction
    template_name = 'payments/payment_list.html'
    context_object_name = 'payments'
    paginate_by = 20

    def get_queryset(self):
        return PaymentTransaction.objects.all().order_by('-payment_date', '-created_at')

class PaymentCreateView(LoginRequiredMixin, AdminRequiredMixin, CreateView):
    model = PaymentTransaction
    template_name = 'payments/payment_form.html'
    fields = ['student', 'group', 'amount', 'payment_date', 'method', 'note']
    success_url = reverse_lazy('payments:payment_list')

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
        from .models import MonthBalanceStatus
        return StudentMonthBalance.objects.filter(
            status__in=['OPEN', 'PARTIAL'] # or use constant if imported
        ).select_related('student', 'group')

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
