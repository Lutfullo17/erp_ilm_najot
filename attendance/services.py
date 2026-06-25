from datetime import date

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404

from groups_app.models import Group

from .models import AttendanceRecord, AttendanceSession, AttendanceStatus


class AttendanceInputError(ValueError):
    pass


def get_teacher_groups(user):
    if not hasattr(user, 'is_authenticated') or not hasattr(user, 'is_teacher'):
        raise PermissionDenied("Foydalanuvchi obyektida kerakli atributlar yo'q.")
    if not user.is_authenticated or not user.is_teacher:
        raise PermissionDenied("Faqat o'qituvchi davomat yurita oladi.")
    return Group.objects.filter(teacher=user, is_active=True).order_by('name')


def get_teacher_group(user, group_id):
    return get_object_or_404(get_teacher_groups(user), pk=group_id)


def parse_attendance_date(value):
    if isinstance(value, date):
        return value

    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise AttendanceInputError("Sana YYYY-MM-DD formatida bo'lishi kerak.")


def get_active_group_students(group):
    return group.groupstudent_set.select_related('student').filter(
        is_active=True,
        student__is_active=True,
    ).order_by('student__last_name', 'student__first_name')


def get_attendance_snapshot(user, group_id, attendance_date):
    group = get_teacher_group(user, group_id)
    attendance_date = parse_attendance_date(attendance_date)

    session = AttendanceSession.objects.filter(group=group, date=attendance_date).first()
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
            'status': record.status if record else None,
            'comment': record.comment if record else '',
        })

    return {
        'group': {'id': group.id, 'name': group.name},
        'date': attendance_date.isoformat(),
        'statuses': [{'value': value, 'label': label} for value, label in AttendanceStatus.choices],
        'students': students,
    }


def normalize_records(records):
    if not isinstance(records, list):
        raise AttendanceInputError("records ro'yxat bo'lishi kerak.")

    normalized = {}
    allowed_statuses = {choice.value for choice in AttendanceStatus}

    for item in records:
        if not isinstance(item, dict):
            raise AttendanceInputError("Har bir davomat yozuvi obyekt bo'lishi kerak.")

        try:
            student_id = int(item.get('student_id'))
        except (TypeError, ValueError):
            raise AttendanceInputError("student_id noto'g'ri butun son bo'lishi kerak.")
        if student_id <= 0:
            raise AttendanceInputError("student_id musbat butun son bo'lishi kerak.")

        status = item.get('status')
        if status not in allowed_statuses:
            raise AttendanceInputError(f'{student_id} uchun status noto\'g\'ri.')

        comment = str(item.get('comment', '')).strip()
        if len(comment) > 255:
            raise AttendanceInputError("Izoh 255 belgidan oshmasligi kerak.")

        normalized[student_id] = {
            'status': status,
            'comment': comment,
        }

    if not normalized:
        raise AttendanceInputError("Kamida bitta davomat yozuvi bo'lishi kerak.")

    return normalized


@transaction.atomic
def save_attendance(user, group_id, attendance_date, records):
    group = get_teacher_group(user, group_id)
    attendance_date = parse_attendance_date(attendance_date)
    normalized = normalize_records(records)

    memberships = list(get_active_group_students(group))
    student_ids = {membership.student_id for membership in memberships}

    if set(normalized) != student_ids:
        raise AttendanceInputError("Davomat guruhdagi barcha faol o'quvchilar uchun yuborilishi kerak.")

    session, _ = AttendanceSession.objects.select_for_update().get_or_create(
        group=group,
        date=attendance_date,
        defaults={'teacher': user},
    )
    session.teacher = user
    session.full_clean()
    session.save()

    for student_id, data in normalized.items():
        record, _ = AttendanceRecord.objects.get_or_create(
            session=session,
            student_id=student_id,
        )
        record.status = data['status']
        record.comment = data['comment']
        record.full_clean()
        record.save()

    return get_attendance_snapshot(user, group.id, attendance_date)
