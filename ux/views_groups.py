import datetime
from decimal import Decimal

from django import forms
from django.contrib import messages
from django.db.models import Count, F, Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from groups_app.models import Group, GroupStudent, Room
from groups_app.views import delete_group as old_delete_group, toggle_pause_group as old_toggle_pause
from payments.models import StudentMonthBalance
from users1.models import AuditLog, User

from . import services
from .base import UxView, ux_login
from .utils import paginate

ADMIN = {'administrator', 'director'}
DAYS = services.DAY_NAMES
DAY_SHORT = {'Dushanba': 'Du', 'Seshanba': 'Se', 'Chorshanba': 'Chor', 'Payshanba': 'Pay', 'Juma': 'Ju', 'Shanba': 'Sha', 'Yakshanba': 'Yak'}
DURATIONS = [('1', '1 soat'), ('1.5', '1,5 soat'), ('2', '2 soat'), ('2.5', '2,5 soat'), ('3', '3 soat')]


class GroupUxForm(forms.ModelForm):
    days = forms.MultipleChoiceField(choices=[(d, d) for d in DAYS], required=True)
    lesson_time = forms.TimeField(required=True, input_formats=['%H:%M', '%H:%M:%S'])
    duration = forms.DecimalField(required=True, max_digits=4, decimal_places=1, min_value=Decimal('0.5'), max_value=Decimal('8'))
    start_date = forms.DateField(required=True)
    monthly_fee = forms.DecimalField(required=True, min_value=0, max_digits=12, decimal_places=2)
    room = forms.TypedChoiceField(choices=[('', '')] + list(Room.choices), coerce=int, empty_value=None, required=False)

    class Meta:
        model = Group
        fields = ['name', 'monthly_fee', 'teacher', 'start_date', 'lesson_time', 'duration', 'room']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['teacher'].queryset = User.objects.filter(role='TEACHER', is_active=True, is_deleted=False).order_by('last_name', 'first_name')
        self.fields['teacher'].required = False
        self.fields['name'].error_messages['required'] = "Guruh nomini kiriting. Masalan: Ingliz tili A1"
        self.fields['name'].error_messages['unique'] = "Bunday nomli guruh allaqachon bor. Boshqa nom tanlang."
        self.fields['monthly_fee'].error_messages.update({'required': "Oylik narxni kiriting. Masalan: 300 000", 'invalid': "Narxni raqam bilan kiriting.", 'min_value': "Narx manfiy bo'lishi mumkin emas.",
            'max_digits': "Narx juda katta. Tekshirib qaytadan kiriting.", 'max_whole_digits': "Narx juda katta. Tekshirib qaytadan kiriting.",
            'max_decimal_places': "Narxni butun so'mda kiriting."})
        self.fields['days'].error_messages['required'] = "Kamida bitta dars kunini tanlang."
        self.fields['lesson_time'].error_messages.update({'required': "Dars boshlanish vaqtini kiriting.", 'invalid': "Vaqtni to'g'ri kiriting. Masalan: 14:30"})
        self.fields['duration'].error_messages.update({'required': "Dars davomiyligini tanlang.", 'invalid': "Davomiylikni to'g'ri kiriting.",
                                                       'min_value': "Dars davomiyligi kamida 0,5 soat.", 'max_value': "Dars davomiyligi 8 soatdan oshmasin."})
        self.fields['start_date'].error_messages.update({'required': "Boshlanish sanasini tanlang.", 'invalid': "Sanani to'g'ri kiriting."})
        self.fields['teacher'].error_messages['invalid_choice'] = "O'qituvchi topilmadi."
        if self.instance.pk and not self.is_bound:
            self.initial['days'] = [d.strip() for d in (self.instance.lesson_days or '').split(',') if d.strip()]

    def clean_name(self):
        return ' '.join(self.cleaned_data['name'].split())

    def clean_monthly_fee(self):
        fee = self.cleaned_data['monthly_fee']
        if fee > Decimal('100000000'):
            raise forms.ValidationError("Narx juda katta. Tekshirib qaytadan kiriting.")
        return fee

    def clean(self):
        data = super().clean()
        days = data.get('days')
        if days:
            self.instance.lesson_days = ', '.join(d for d in DAYS if d in days)
        return data


def _form_ctx(form, group=None):
    teachers = form.fields['teacher'].queryset
    return {'form': form, 'group': group, 'teachers': teachers, 'rooms': Room.choices,
            'days': [(d, DAY_SHORT[d]) for d in DAYS], 'durations': DURATIONS,
            'presets': [('Dushanba, Chorshanba, Juma', 'Du-Chor-Ju'), ('Seshanba, Payshanba, Shanba', 'Sesh-Pay-Shan'),
                        ('Dushanba, Chorshanba', 'Du-Chor'), ('Seshanba, Payshanba', 'Sesh-Pay'), ('Juma, Shanba', 'Juma-Shan')]}


class GroupsView(UxView):
    roles = ADMIN
    template_name = 'new/groups.html'

    def get(self, request):
        qs = Group.objects.select_related('teacher').annotate(n=Count(
            'groupstudent', filter=Q(groupstudent__is_active=True, groupstudent__student__is_active=True)))
        flt = request.GET.get('f', 'active')
        if flt == 'active':
            qs = qs.filter(is_active=True, is_paused=False)
        elif flt == 'paused':
            qs = qs.filter(is_paused=True)
        elif flt == 'closed':
            qs = qs.filter(is_active=False)
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(teacher__first_name__icontains=q) | Q(teacher__last_name__icontains=q))
        page, qs_params = paginate(request, qs.order_by('name'), 20)
        filters = [('active', 'Faol'), ('paused', 'Pauzada'), ('closed', 'Yopilgan'), ('all', 'Hammasi')]
        return self.render(request, {'page': page, 'qs': qs_params, 'q': q, 'flt': flt, 'filters': filters, 'count': page.paginator.count})


class GroupFormBase(UxView):
    roles = ADMIN
    template_name = 'new/group_form.html'


class GroupNewView(GroupFormBase):
    def get(self, request):
        return self.render(request, _form_ctx(GroupUxForm(initial={'start_date': datetime.date.today(), 'duration': '1.5'})))

    def post(self, request):
        form = GroupUxForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Ba'zi maydonlar noto'g'ri to'ldirilgan. Qizil yozuvlarni tuzating.")
            return self.render(request, {**_form_ctx(form), 'open_step': _error_step(form)}, status=400)
        group = form.save(commit=False)
        group.save()
        AuditLog.objects.create(user=request.user, role=request.user.role, action="Guruh yaratildi",
                                new_data={'group': group.name, 'teacher': group.teacher_id, 'room': group.room,
                                          'lesson_time': str(group.lesson_time), 'duration': str(group.duration)})
        messages.success(request, f"'{group.name}' guruhi yaratildi. Endi o'quvchilarni qo'shing.")
        return redirect('new:group', pk=group.pk)


class GroupEditView(GroupFormBase):
    def get(self, request, pk):
        group = get_object_or_404(Group, pk=pk)
        return self.render(request, _form_ctx(GroupUxForm(instance=group), group))

    def post(self, request, pk):
        group = get_object_or_404(Group, pk=pk)
        old = {'teacher': group.teacher_id, 'room': group.room, 'lesson_time': str(group.lesson_time), 'duration': str(group.duration)}
        form = GroupUxForm(request.POST, instance=group)
        if not form.is_valid():
            messages.error(request, "Ba'zi maydonlar noto'g'ri to'ldirilgan. Qizil yozuvlarni tuzating.")
            return self.render(request, {**_form_ctx(form, group), 'open_step': _error_step(form)}, status=400)
        group = form.save()
        AuditLog.objects.create(user=request.user, role=request.user.role, action="Guruh tahrirlandi", old_data=old,
                                new_data={'teacher': group.teacher_id, 'room': group.room, 'lesson_time': str(group.lesson_time), 'duration': str(group.duration)})
        messages.success(request, "O'zgarishlar saqlandi.")
        return redirect('new:group', pk=group.pk)


def _error_step(form):
    errs = set(form.errors)
    if errs & {'name', 'monthly_fee'}:
        return 1
    if errs & {'teacher'}:
        return 2
    if errs & {'days', 'lesson_time', 'duration', 'start_date'}:
        return 3
    return 4


class GroupDetailView(UxView):
    roles = ADMIN
    template_name = 'new/group_detail.html'

    def get(self, request, pk):
        group = get_object_or_404(Group.objects.select_related('teacher'), pk=pk)
        members = list(GroupStudent.objects.filter(group=group, is_active=True, student__is_active=True)
                       .select_related('student').order_by('student__last_name', 'student__first_name'))
        debts = {r['student_id']: r['t'] for r in StudentMonthBalance.objects.debts().filter(group=group)
                 .values('student_id').annotate(t=Sum(F('required_amount') - F('paid_amount')))}
        for m in members:
            m.debt = debts.get(m.student_id, 0)
        total_debt = sum((m.debt for m in members), Decimal('0'))
        member_ids = [m.student_id for m in members]
        from students.models import Student
        free = Student.objects.filter(is_active=True).exclude(pk__in=member_ids).order_by('last_name', 'first_name')[:300]
        return self.render(request, {'group': group, 'members': members, 'total_debt': total_debt, 'free_students': free,
                                     'debtors': sum(1 for m in members if m.debt)})


@require_POST
@ux_login(ADMIN)
def group_pause(request, pk):
    old_toggle_pause(request, pk)
    return redirect('new:group', pk=pk)


@require_POST
@ux_login({'director'})
def group_delete(request, pk):
    old_delete_group(request, pk)
    return redirect('new:groups')


@require_GET
@ux_login(ADMIN, json_mode=True)
def api_check_slot(request):
    """B7: tanlangan kun/vaqtda qaysi xonalar band, o'qituvchi bandmi (faqat o'qish)."""
    days = [d for d in request.GET.get('days', '').split(',') if d in DAYS]
    try:
        start = datetime.datetime.strptime(request.GET.get('time', ''), '%H:%M').time()
        duration = Decimal(request.GET.get('duration', ''))
    except (ValueError, ArithmeticError):
        return JsonResponse({'rooms': [{'id': v, 'label': l, 'free': True} for v, l in Room.choices], 'teacher_busy': ''})
    if not days or duration <= 0:
        return JsonResponse({'rooms': [{'id': v, 'label': l, 'free': True} for v, l in Room.choices], 'teacher_busy': ''})
    exclude = request.GET.get('exclude')
    exclude = int(exclude) if exclude and exclude.isdigit() else None
    end = services.end_from(start, duration)
    clashes = services.slot_conflicts(days, start, end, exclude)
    busy = {}
    for g in clashes:
        if g.room:
            busy.setdefault(g.room, g.name)
    teacher_id = request.GET.get('teacher')
    teacher_busy = ''
    if teacher_id and teacher_id.isdigit():
        for g in clashes:
            if g.teacher_id == int(teacher_id):
                teacher_busy = f"Bu o'qituvchi shu vaqtda '{g.name}' guruhida dars beradi."
                break
    return JsonResponse({
        'rooms': [{'id': v, 'label': l, 'free': v not in busy, 'busy_by': busy.get(v, '')} for v, l in Room.choices],
        'teacher_busy': teacher_busy,
    })
