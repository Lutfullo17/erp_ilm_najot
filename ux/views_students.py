import datetime
from decimal import Decimal

from django.contrib import messages
from django.db.models import Count, F, Q, Sum
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from attendance.models import AttendanceRecord
from bot.models import TelegramUser
from groups_app.models import Group, GroupStudent
from groups_app.services import MembershipError, add_student, remove_student
from payments.models import PaymentTransaction, StudentMonthBalance
from students.models import Student
from students.views import delete_student as old_delete_student
from users1.models import AuditLog

from .base import UxView, ux_login
from .forms import UxStudentForm
from users1.jsonutil import to_id

from .utils import paginate

ADMIN = {'administrator', 'director'}


def _audit(request, action, **kw):
    AuditLog.objects.create(user=request.user, role=request.user.role, action=action, **kw)


class StudentsView(UxView):
    roles = ADMIN
    template_name = 'new/students.html'

    def get(self, request):
        qs = Student.objects.filter(is_active=True)
        q = request.GET.get('q', '').strip()
        if q:
            digits = ''.join(ch for ch in q if ch.isdigit())
            cond = Q(first_name__icontains=q) | Q(last_name__icontains=q)
            parts = q.split()
            if len(parts) >= 2:
                cond |= Q(first_name__icontains=parts[0], last_name__icontains=parts[1]) | Q(
                    first_name__icontains=parts[1], last_name__icontains=parts[0])
            if len(digits) >= 3:
                cond |= Q(phone__icontains=digits[-9:]) | Q(parent_phone__icontains=digits[-9:])
            qs = qs.filter(cond)
        flt = request.GET.get('f', '')
        debtors = StudentMonthBalance.objects.debts().current_members().values('student_id')
        if flt == 'debt':
            qs = qs.filter(pk__in=debtors)
        elif flt == 'nogroup':
            qs = qs.exclude(pk__in=GroupStudent.objects.filter(is_active=True, group__is_active=True).values('student_id'))
        elif flt == 'frozen':
            qs = qs.filter(status=Student.Status.FROZEN)
        gid = to_id(request.GET.get('group'))
        if gid:
            qs = qs.filter(groupstudent__group_id=gid, groupstudent__is_active=True)
        qs = qs.order_by('last_name', 'first_name').distinct()
        page, qs_params = paginate(request, qs, 20)
        ids = [s.pk for s in page.object_list]
        debt_map = {r['student_id']: r['t'] for r in StudentMonthBalance.objects.debts().filter(student_id__in=ids)
                    .values('student_id').annotate(t=Sum(F('required_amount') - F('paid_amount')))}
        groups_map = {}
        for m in GroupStudent.objects.filter(student_id__in=ids, is_active=True, group__is_active=True).select_related('group'):
            groups_map.setdefault(m.student_id, []).append(m.group.name)
        for s in page.object_list:
            s.debt = debt_map.get(s.pk, 0)
            s.group_names = groups_map.get(s.pk, [])
        filters = [('', 'Hammasi'), ('debt', 'Faqat qarzdorlar'), ('nogroup', 'Guruhsiz'), ('frozen', 'Pauzadagilar')]
        return self.render(request, {'page': page, 'qs': qs_params, 'q': q, 'flt': flt, 'group_id': gid, 'filters': filters,
                                     'groups': Group.objects.filter(is_active=True).order_by('name'), 'count': page.paginator.count,
                                     'total': Student.objects.filter(is_active=True).count()})


class StudentNewView(UxView):
    roles = ADMIN
    template_name = 'new/student_form.html'

    def _ctx(self, form, edit=False, student=None):
        return {'form': form, 'edit': edit, 'student': student,
                'groups': Group.objects.filter(is_active=True).order_by('name'),
                'dup': getattr(form, 'duplicate_of', None)}

    def get(self, request):
        initial = {}
        gid = request.GET.get('group')
        return self.render(request, {**self._ctx(UxStudentForm(initial=initial)), 'pre_group': gid or ''})

    def post(self, request):
        form = UxStudentForm(request.POST)
        group = None
        gid = request.POST.get('group')
        if to_id(gid):
            group = Group.objects.filter(pk=to_id(gid), is_active=True).first()
        if not form.is_valid():
            messages.error(request, "Ba'zi maydonlar noto'g'ri to'ldirilgan. Qizil yozuvlarni tuzating.")
            return self.render(request, {**self._ctx(form), 'pre_group': gid or '', 'open_step': _first_error_step(form)}, status=400)
        student = form.save()
        _audit(request, f"O'quvchi qo'shildi: {student}")
        if group:
            try:
                add_student(group, student, request.user)
            except MembershipError as exc:
                messages.warning(request, f"O'quvchi qo'shildi, lekin guruhga qo'shilmadi: {exc}")
        messages.success(request, f"{student} muvaffaqiyatli qo'shildi.")
        return redirect(reverse('new:student', args=[student.pk]) + '?new=1')


def _first_error_step(form):
    step2 = {'parent_phone', 'birth_date', 'gender'}
    step3 = {'has_discount', 'discount_type', 'discount_value'}
    errs = set(form.errors)
    if errs & {'full_name', 'phone'}:
        return 1
    if errs & step2:
        return 2
    if errs & step3:
        return 3
    return 1


class StudentEditView(StudentNewView):
    def get(self, request, pk):
        student = get_object_or_404(Student, pk=pk, is_deleted=False)
        return self.render(request, {**self._ctx(UxStudentForm(instance=student), True, student), 'pre_group': ''})

    def post(self, request, pk):
        student = get_object_or_404(Student, pk=pk, is_deleted=False)
        fields = ('status', 'has_discount', 'discount_type', 'discount_value')
        before = {k: str(getattr(student, k)) for k in fields}
        form = UxStudentForm(request.POST, instance=student)
        if not form.is_valid():
            messages.error(request, "Ba'zi maydonlar noto'g'ri to'ldirilgan. Qizil yozuvlarni tuzating.")
            return self.render(request, {**self._ctx(form, True, student), 'pre_group': '', 'open_step': _first_error_step(form)}, status=400)
        student = form.save()
        after = {k: str(getattr(student, k)) for k in fields}
        if before != after:
            _audit(request, f"O'quvchi holati/chegirmasi o'zgardi: {student}", old_data=before, new_data=after)
        messages.success(request, "O'zgarishlar saqlandi.")
        return redirect('new:student', pk=student.pk)


class StudentDetailView(UxView):
    roles = ADMIN
    template_name = 'new/student_detail.html'

    def get(self, request, pk):
        student = get_object_or_404(Student, pk=pk, is_deleted=False)
        debts = (StudentMonthBalance.objects.debts().filter(student=student).values('group_id')
                 .annotate(t=Sum(F('required_amount') - F('paid_amount')), n=Count('id')))
        debt_map = {d['group_id']: d for d in debts}
        memberships = list(GroupStudent.objects.filter(student=student, is_active=True).select_related('group'))
        for m in memberships:
            d = debt_map.get(m.group_id)
            m.debt = d['t'] if d else 0
            m.months = d['n'] if d else 0
        total_debt = sum((d['t'] for d in debt_map.values()), Decimal('0'))
        main_group = max(debt_map.items(), key=lambda kv: kv[1]['t'])[0] if debt_map else (memberships[0].group_id if memberships else '')
        member_ids = [m.group_id for m in memberships]
        payments = PaymentTransaction.objects.filter(student=student).select_related('group').order_by('-payment_date', '-created_at')[:5]
        att = AttendanceRecord.objects.filter(student=student).select_related('session__group').order_by('-session__date')[:8]
        tg = TelegramUser.objects.filter(student=student, is_verified=True).first()
        return self.render(request, {
            'student': student, 'memberships': memberships, 'total_debt': total_debt, 'main_group': main_group,
            'payments': payments, 'attendance': att, 'telegram': tg, 'is_new': request.GET.get('new') == '1',
            'free_groups': Group.objects.filter(is_active=True).exclude(pk__in=member_ids).order_by('name'),
        })


@require_POST
@ux_login(ADMIN, json_mode=True)
def api_student_group(request, pk):
    """Guruhga qo'shish / chiqarish (mavjud servislar). JSON: {action: add|remove, group_id}."""
    from .base import json_body
    student = get_object_or_404(Student, pk=pk, is_deleted=False)
    data = json_body(request) or {}
    group = Group.objects.filter(pk=to_id(data.get('group_id'))).first() if to_id(data.get('group_id')) else None
    if group is None:
        return JsonResponse({'detail': 'Guruh topilmadi.'}, status=404)
    try:
        if data.get('action') == 'add':
            add_student(group, student, request.user)
        elif data.get('action') == 'remove':
            remove_student(group, student, request.user)
        else:
            return JsonResponse({'detail': "Amal noto'g'ri."}, status=400)
    except MembershipError as exc:
        return JsonResponse({'detail': str(exc)}, status=400)
    return JsonResponse({'ok': True})


@require_POST
@ux_login({'director'})
def student_delete(request, pk):
    """Direktor o'quvchini o'chiradi (eski view ning mantig'i: soft-delete + audit)."""
    old_delete_student(request, pk)
    return redirect('new:students')
