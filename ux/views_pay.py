import datetime
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Count, F, Q, Sum
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from groups_app.models import Group, GroupStudent
from payments.billing import effective_fee
from payments.models import PaymentMethod, PaymentTransaction, StudentMonthBalance
from payments.services import PaymentInputError, UNDO_MINUTES, apply_payment, delete_payment, serialize_money
from payments.views import _payable_students
from students.models import Student

from .base import UxView, json_body, ux_login
from users1.jsonutil import to_id

from .utils import paginate, safe_next

ADMIN = {'administrator', 'director'}


def _debt_by_group(student):
    rows = (StudentMonthBalance.objects.debts().filter(student=student)
            .values('group_id').annotate(total=Sum(F('required_amount') - F('paid_amount')), months=Count('id')))
    return {r['group_id']: r for r in rows}


def student_pay_info(student):
    """O'quvchining to'lov qabul qilinadigan guruhlari va ularning qarzi."""
    debts = _debt_by_group(student)
    groups, seen = [], set()
    if student.is_active:
        for m in GroupStudent.objects.filter(student=student, is_active=True, group__is_active=True).select_related('group'):
            g = m.group
            d = debts.get(g.pk)
            seen.add(g.pk)
            groups.append({'id': g.pk, 'name': g.name, 'fee': serialize_money(effective_fee(student, g)),
                           'debt': serialize_money(d['total']) if d else '0', 'months': d['months'] if d else 0,
                           'has_fee': g.monthly_fee is not None, 'former': False})
    for gid, d in debts.items():
        if gid in seen:
            continue
        g = Group.objects.filter(pk=gid).first()
        if g:
            groups.append({'id': g.pk, 'name': g.name + " (sobiq guruh)", 'fee': serialize_money(effective_fee(student, g)),
                           'debt': serialize_money(d['total']), 'months': d['months'], 'has_fee': True, 'former': True})
    groups.sort(key=lambda x: -Decimal(x['debt']))
    return {'id': student.pk, 'name': f'{student.first_name} {student.last_name}', 'phone': student.phone or student.parent_phone,
            'groups': groups}


class PayView(UxView):
    roles = ADMIN
    template_name = 'new/pay.html'

    def get(self, request):
        today = timezone.localdate()
        max_back = 36500 if request.user.is_director else getattr(settings, 'PAYMENT_BACKDATE_DAYS', 7)
        pre = None
        sid = to_id(request.GET.get('student'))
        if sid:
            st = _payable_students().filter(pk=sid).first()
            if st:
                pre = student_pay_info(st)
        return self.render(request, {
            'today': today.isoformat(), 'min_date': (today - datetime.timedelta(days=max_back)).isoformat(),
            'max_back': max_back, 'pre': pre, 'pre_group': request.GET.get('group', ''),
            'methods': PaymentMethod.choices, 'undo_minutes': UNDO_MINUTES,
        })


@require_GET
@ux_login(ADMIN, json_mode=True)
def api_pay_search(request):
    q = request.GET.get('q', '').strip()
    if len(q) < 2:
        return JsonResponse({'students': []})
    digits = ''.join(ch for ch in q if ch.isdigit())
    cond = Q(first_name__icontains=q) | Q(last_name__icontains=q)
    parts = q.split()
    if len(parts) >= 2:
        cond |= Q(first_name__icontains=parts[0], last_name__icontains=parts[1]) | Q(
            first_name__icontains=parts[1], last_name__icontains=parts[0])
    if len(digits) >= 3:
        cond |= Q(phone__icontains=digits[-9:]) | Q(parent_phone__icontains=digits[-9:])
    students = list(_payable_students().filter(cond).distinct()[:10])
    debts = {r['student_id']: r['total'] for r in StudentMonthBalance.objects.debts().filter(student__in=students)
             .values('student_id').annotate(total=Sum(F('required_amount') - F('paid_amount')))}
    return JsonResponse({'students': [
        {'id': s.pk, 'name': f'{s.first_name} {s.last_name}', 'phone': s.phone or s.parent_phone,
         'debt': serialize_money(debts.get(s.pk, 0))} for s in students]})


@require_GET
@ux_login(ADMIN, json_mode=True)
def api_pay_info(request, pk):
    student = get_object_or_404(_payable_students(), pk=pk)
    return JsonResponse(student_pay_info(student))


@require_POST
@ux_login(ADMIN, json_mode=True)
def api_pay_create(request):
    """B3: mavjud apply_payment() ni chaqiradi (idempotentlik kaliti bilan)."""
    data = json_body(request)
    if data is None:
        return JsonResponse({'detail': "So'rov noto'g'ri."}, status=400)
    try:
        result = apply_payment(
            request.user, data.get('student_id'), data.get('group_id'), data.get('amount'),
            data.get('payment_date') or None, data.get('method') or PaymentMethod.CASH, data.get('note', ''),
            idempotency_key=data.get('idempotency_key'),
        )
    except PaymentInputError as exc:
        return JsonResponse({'detail': str(exc)}, status=400)
    except PermissionDenied:
        return JsonResponse({'detail': "Ruxsat yo'q."}, status=403)
    except Http404:
        return JsonResponse({'detail': "O'quvchi yoki guruh topilmadi."}, status=404)
    pay = PaymentTransaction.objects.select_related('student', 'group').get(pk=result['payment']['id'])
    debts = _debt_by_group(pay.student)
    left = debts.get(pay.group_id)
    result['payment']['receipt_url'] = reverse('new:receipt', args=[pay.pk])
    result['payment']['undo_url'] = reverse('new:api_pay_undo', args=[pay.pk])
    result['left_debt'] = serialize_money(left['total']) if left else '0'
    result['total_left_debt'] = serialize_money(sum((d['total'] for d in debts.values()), Decimal('0')))
    return JsonResponse(result, status=200 if result.get('duplicate') else 201)


@require_POST
@ux_login(ADMIN, json_mode=True)
def api_pay_undo(request, pk):
    """B8: administrator o'zi qabul qilgan to'lovni 5 daqiqa ichida bekor qiladi."""
    try:
        delete_payment(request.user, pk, undo=True)
    except PermissionDenied as exc:
        return JsonResponse({'detail': str(exc)}, status=403)
    except Http404:
        return JsonResponse({'detail': "To'lov topilmadi (allaqachon bekor qilingan bo'lishi mumkin)."}, status=404)
    return JsonResponse({'ok': True})


# --------------------------------------------------------------- Qarzdorlar

class DebtorsView(UxView):
    roles = ADMIN
    template_name = 'new/debtors.html'

    def get(self, request):
        qs = StudentMonthBalance.objects.debts().current_members()
        group_id = to_id(request.GET.get('group'))
        if group_id:
            qs = qs.filter(group_id=group_id)
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(student__first_name__icontains=q) | Q(student__last_name__icontains=q) | Q(student__phone__icontains=q))
        rows = (qs.values('student_id', 'student__first_name', 'student__last_name', 'student__phone', 'student__parent_phone')
                .annotate(total=Sum(F('required_amount') - F('paid_amount')), months=Count('id')).order_by('-total'))
        flt = request.GET.get('f', '')
        if flt == '2':
            rows = rows.filter(months__gte=2)
        elif flt == '1':
            rows = rows.filter(months=1)
        total_debt = sum((r['total'] for r in rows), Decimal('0')) if rows else Decimal('0')
        page, qs_params = paginate(request, rows, 20)
        ids = [r['student_id'] for r in page.object_list]
        group_rows = (StudentMonthBalance.objects.debts().current_members().filter(student_id__in=ids)
                      .values('student_id', 'group_id', 'group__name').annotate(total=Sum(F('required_amount') - F('paid_amount'))))
        by_student = {}
        for g in group_rows:
            by_student.setdefault(g['student_id'], []).append(g)
        items = []
        for r in page.object_list:
            groups = sorted(by_student.get(r['student_id'], []), key=lambda x: -x['total'])
            items.append({'r': r, 'groups': groups, 'main_group': groups[0]['group_id'] if groups else ''})
        return self.render(request, {
            'items': items, 'page': page, 'qs': qs_params, 'q': q, 'flt': flt, 'group_id': group_id,
            'total_debt': total_debt, 'groups': Group.objects.filter(is_active=True).order_by('name'),
            'count': page.paginator.count,
        })


# --------------------------------------------------------------- Tarix

class PaymentsView(UxView):
    roles = ADMIN
    template_name = 'new/payments.html'

    def get(self, request):
        today = timezone.localdate()
        qs = PaymentTransaction.objects.select_related('student', 'group', 'created_by')
        if not request.user.is_director:
            qs = qs.filter(created_by=request.user)
        period = request.GET.get('p', 'today')
        if period == 'today':
            qs = qs.filter(payment_date=today)
        elif period == 'week':
            qs = qs.filter(payment_date__gte=today - datetime.timedelta(days=today.weekday()))
        elif period == 'month':
            qs = qs.filter(payment_date__year=today.year, payment_date__month=today.month)
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(student__first_name__icontains=q) | Q(student__last_name__icontains=q) | Q(group__name__icontains=q))
        total = qs.aggregate(s=Sum('amount'))['s'] or Decimal('0')
        qs = qs.order_by('-payment_date', '-created_at')
        page, qs_params = paginate(request, qs, 20)
        now = timezone.now()
        for p in page.object_list:
            p.can_undo = (not request.user.is_director and p.created_by_id == request.user.pk
                          and now - p.created_at <= datetime.timedelta(minutes=UNDO_MINUTES))
        periods = [('today', 'Bugun'), ('week', 'Shu hafta'), ('month', 'Shu oy'), ('all', 'Hammasi')]
        return self.render(request, {'page': page, 'qs': qs_params, 'q': q, 'period': period, 'total': total,
                                     'undo_minutes': UNDO_MINUTES, 'periods': periods})


@require_POST
@ux_login(ADMIN)
def payment_delete(request, pk):
    """Direktor to'lovni o'chiradi (yoki administrator 5 daqiqa ichida bekor qiladi)."""
    try:
        delete_payment(request.user, pk, undo=not request.user.is_director)
        messages.success(request, "To'lov bekor qilindi. O'quvchining hisobi qayta hisoblandi.")
    except PermissionDenied as exc:
        messages.error(request, str(exc))
    except Http404:
        messages.error(request, "To'lov topilmadi.")
    return redirect(safe_next(request, reverse('new:payments')))


@ux_login(ADMIN)
def receipt(request, pk):
    pay = get_object_or_404(PaymentTransaction.objects.select_related('student', 'group', 'created_by'), pk=pk)
    if not request.user.is_director and pay.created_by_id != request.user.pk:
        raise Http404
    return render(request, 'new/receipt.html', {'pay': pay})
