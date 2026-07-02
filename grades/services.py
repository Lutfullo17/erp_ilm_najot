from datetime import date
from decimal import Decimal, InvalidOperation

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404

from groups_app.models import Group

from .models import GradeRecord, GradeSession


class GradeInputError(ValueError):
    pass


def get_teacher_groups(user):
    if not user.is_authenticated or not user.is_teacher:
        raise PermissionDenied("Faqat o'qituvchi baho qo'ya oladi.")

    return Group.objects.filter(teacher=user, is_active=True).order_by('name')


def get_teacher_group(user, group_id):
    return get_object_or_404(get_teacher_groups(user), pk=group_id)


def parse_grade_date(value):
    if isinstance(value, date):
        return value

    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise GradeInputError("Sana YYYY-MM-DD formatida bo'lishi kerak.")


def normalize_title(value):
    title = str(value or 'Dars bahosi').strip()
    if not title:
        raise GradeInputError("Baholash nomi bo'sh bo'lmasligi kerak.")
    return title[:150]


def get_active_group_students(group):
    return group.groupstudent_set.select_related('student').filter(
        is_active=True,
        student__is_active=True,
    ).order_by('student__last_name', 'student__first_name')


def serialize_percentage(value):
    normalized = value.normalize()
    return str(normalized.quantize(Decimal('1')) if normalized == normalized.to_integral() else normalized)


def get_grade_snapshot(user, group_id, grade_date, title='Dars bahosi'):
    group = get_teacher_group(user, group_id)
    grade_date = parse_grade_date(grade_date)
    title = normalize_title(title)

    session = GradeSession.objects.filter(group=group, date=grade_date, title=title).first()
    existing_records = {}
    if session:
        existing_records = {
            record.student_id: record
            for record in session.records.select_related('student')
        }

    students = []
    for membership in get_active_group_students(group):
        record = existing_records.get(membership.student_id)
        students.append({
            'id': membership.student_id,
            'full_name': str(membership.student),
            'percentage': serialize_percentage(record.percentage) if record else None,
            'comment': record.comment if record else '',
            'is_locked': record is not None,
        })

    return {
        'group': {'id': group.id, 'name': group.name},
        'date': grade_date.isoformat(),
        'title': title,
        'students': students,
    }


def parse_percentage(value, student_id):
    try:
        percentage = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise GradeInputError(f'{student_id} uchun foiz noto\'g\'ri.')

    if percentage < 0 or percentage > 100:
        raise GradeInputError(f'{student_id} uchun foiz 0 dan 100 gacha bo\'lishi kerak.')

    return percentage.quantize(Decimal('0.01'))


def normalize_records(records):
    if not isinstance(records, list):
        raise GradeInputError("records ro'yxat bo'lishi kerak.")

    normalized = {}

    for item in records:
        if not isinstance(item, dict):
            raise GradeInputError("Har bir baho yozuvi obyekt bo'lishi kerak.")

        try:
            student_id = int(item.get('student_id'))
        except (TypeError, ValueError):
            raise GradeInputError("student_id noto'g'ri.")

        normalized[student_id] = {
            'percentage': parse_percentage(item.get('percentage'), student_id),
            'comment': str(item.get('comment', '')).strip()[:255],
        }

    return normalized


@transaction.atomic
def save_grades(user, group_id, grade_date, title, records):
    group = get_teacher_group(user, group_id)
    grade_date = parse_grade_date(grade_date)
    title = normalize_title(title)
    normalized = normalize_records(records)

    memberships = list(get_active_group_students(group))
    student_ids = {membership.student_id for membership in memberships}

    if set(normalized) != student_ids:
        raise GradeInputError("Baholar guruhdagi barcha faol o'quvchilar uchun yuborilishi kerak.")

    session, _ = GradeSession.objects.select_for_update().get_or_create(
        group=group,
        date=grade_date,
        title=title,
        defaults={'teacher': user},
    )
    session.teacher = user
    session.full_clean()
    session.save()

    for student_id, data in normalized.items():
        from students.models import Student
        student = Student.objects.filter(pk=student_id).first()
        record, created = GradeRecord.objects.get_or_create(
            session=session,
            student_id=student_id,
            defaults=data,
        )
        if not created:
            raise GradeInputError(f"{student} uchun baho allaqachon qo'yilgan. O'zgartirib bo'lmaydi.")
        record.full_clean()
        record.save()

    return get_grade_snapshot(user, group.id, grade_date, title)
