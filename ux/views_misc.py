from django.db.models import Q
from django.http import JsonResponse
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from groups_app.models import Group
from students.models import Student
from users1.models import User

from .base import json_body, ux_login
from .models import Feedback
from .nav import role_of


@require_GET
@ux_login(json_mode=True)
def api_search(request):
    """B1: global qidiruv (faqat o'qish). O'quvchi, guruh, (direktor uchun) o'qituvchi."""
    q = request.GET.get('q', '').strip()
    role = role_of(request.user)
    if len(q) < 2:
        return JsonResponse({'groups': []})
    digits = ''.join(ch for ch in q if ch.isdigit())
    groups = []

    if role == 'teacher':
        mine = Group.objects.filter(teacher=request.user, is_active=True, name__icontains=q)[:8]
        groups.append({'title': 'Guruhlarim', 'items': [
            {'title': g.name, 'sub': g.lesson_days or '', 'url': reverse('new:my_group', args=[g.pk]),
             'actions': [{'label': 'Davomat', 'url': reverse('new:attendance_mark', args=[g.pk])}]} for g in mine]})
        return JsonResponse({'groups': groups})

    cond = Q(first_name__icontains=q) | Q(last_name__icontains=q)
    parts = q.split()
    if len(parts) >= 2:
        cond |= Q(first_name__icontains=parts[0], last_name__icontains=parts[1]) | Q(
            first_name__icontains=parts[1], last_name__icontains=parts[0])
    if len(digits) >= 3:
        cond |= Q(phone__icontains=digits[-9:]) | Q(parent_phone__icontains=digits[-9:])
    students = Student.objects.filter(cond, is_active=True).distinct()[:8]
    groups.append({'title': "O'quvchilar", 'items': [
        {'title': f'{s.first_name} {s.last_name}', 'sub': s.phone or s.parent_phone or '',
         'url': reverse('new:student', args=[s.pk]),
         'actions': [{'label': "To'lov qabul qilish", 'url': reverse('new:pay') + f'?student={s.pk}'}]} for s in students]})

    grp = Group.objects.filter(name__icontains=q, is_active=True).select_related('teacher')[:6]
    groups.append({'title': 'Guruhlar', 'items': [
        {'title': g.name, 'sub': ' · '.join(x for x in [g.teacher.get_full_name() if g.teacher else '', g.lesson_days] if x),
         'url': reverse('new:group', args=[g.pk]),
         'actions': [{'label': 'Davomat', 'url': reverse('new:attendance_mark', args=[g.pk])}]} for g in grp]})

    if role == 'director':
        teachers = User.objects.filter(role='TEACHER', is_deleted=False).filter(
            Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(username__icontains=q))[:5]
        groups.append({'title': "O'qituvchilar", 'items': [
            {'title': t.get_full_name() or t.username, 'sub': t.phone or '', 'url': reverse('new:staff_teacher', args=[t.pk]),
             'actions': []} for t in teachers]})
    return JsonResponse({
        'groups': groups,
        'empty_url': reverse('new:student_new'), 'empty_label': "Yangi o'quvchi qo'shish",
    })


@require_POST
@ux_login(json_mode=True)
def feedback(request):
    """B9: foydalanuvchi fikri."""
    data = json_body(request)
    if data is None:
        return JsonResponse({'detail': "So'rov noto'g'ri."}, status=400)
    message = str(data.get('message', '')).strip()
    if len(message) < 3:
        return JsonResponse({'detail': 'Iltimos, fikringizni yozing.'}, status=400)
    Feedback.objects.create(user=request.user, page=str(data.get('page', ''))[:255], message=message[:1000])
    return JsonResponse({'ok': True})
