from django.db import transaction

from students.models import Student
from users1.models import AuditLog

from .models import Group, GroupStudent


class MembershipError(ValueError):
    pass


@transaction.atomic
def add_student(group, student, user=None):
    """O'quvchini guruhga qo'shadi (yoki qayta faollashtiradi). (membership, created) qaytaradi."""
    if not group.is_active:
        raise MembershipError("Guruh faol emas.")
    if student.is_deleted or not student.is_active or student.status == Student.Status.LEFT:
        raise MembershipError("O'quvchi faol emas (o'chirilgan yoki ketgan).")
    membership, created = GroupStudent.objects.get_or_create(group=group, student=student)
    if not created and not membership.is_active:
        membership.is_active = True
        membership.save()
        created = False
    elif not created:
        return membership, False
    if user is not None:
        AuditLog.objects.create(
            user=user, role=user.role, action="O'quvchi guruhga qo'shildi",
            new_data={'student_id': student.pk, 'group_id': group.pk},
        )
    return membership, True


@transaction.atomic
def remove_student(group, student, user=None):
    """A'zolikni nofaol qiladi (signal chiqish sanasini yozadi va hisobni to'xtatadi)."""
    membership = GroupStudent.objects.filter(group=group, student=student, is_active=True).first()
    if membership is None:
        raise MembershipError("O'quvchi bu guruhda faol emas.")
    membership.is_active = False
    membership.save()
    if user is not None:
        AuditLog.objects.create(
            user=user, role=user.role, action="O'quvchi guruhdan chiqarildi",
            old_data={'student_id': student.pk, 'group_id': group.pk},
        )
    return membership
