# To'lov xabarnomalari payments/services.py ichida yuboriladi (takrorlanmasligi uchun signal yo'q).
#
# Quyidagi signallar hisob-kitobga ta'sir qiluvchi har qanday o'zgarishda (sayt, Django admin,
# shell) oylik balanslarni billing.sync_* orqali qayta hisoblaydi.
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

from groups_app.models import Group, GroupStudent
from students.models import Student

from .billing import sync_group, sync_pair, sync_student
from .models import BillingPause, PaymentTransaction

GROUP_FIELDS = ('monthly_fee', 'start_date', 'is_paused', 'is_active')
STUDENT_FIELDS = ('has_discount', 'discount_type', 'discount_value', 'status', 'is_active')
MEMBERSHIP_FIELDS = ('is_active', 'joined_at', 'left_at')


def _snapshot(sender, instance, fields):
    if not instance.pk:
        return None
    old = sender.objects.filter(pk=instance.pk).values(*fields).first()
    return old


def _changed(instance, fields):
    old = getattr(instance, '_billing_old', None)
    if old is None:
        return set(fields)
    return {f for f in fields if old[f] != getattr(instance, f)}


def _open_pause(start, reason, student=None, group=None):
    if not BillingPause.objects.filter(student=student, group=group, end_date__isnull=True).exists():
        pause = BillingPause(student=student, group=group, start_date=start, reason=reason)
        pause._skip_sync = True  # chaqiruvchi o'zi sync qiladi
        pause.save()


def _close_pause(end, student=None, group=None):
    for pause in BillingPause.objects.filter(student=student, group=group, end_date__isnull=True):
        pause.end_date = max(end, pause.start_date)
        pause._skip_sync = True
        pause.save(update_fields=['end_date'])


# ------------------------------------------------------------------ Group

@receiver(pre_save, sender=Group)
def group_pre_save(sender, instance, raw=False, **kwargs):
    if not raw:
        instance._billing_old = _snapshot(sender, instance, GROUP_FIELDS)


@receiver(post_save, sender=Group)
def group_post_save(sender, instance, created, raw=False, **kwargs):
    if raw or created:
        return
    changed = _changed(instance, GROUP_FIELDS)
    if not changed:
        return
    today = timezone.localdate()
    if 'is_paused' in changed:
        if instance.is_paused:
            _open_pause(today, "Guruh vaqtincha to'xtatilgan", group=instance)
        else:
            _close_pause(today, group=instance)
    sync_group(instance)


# ------------------------------------------------------------------ Student

@receiver(pre_save, sender=Student)
def student_pre_save(sender, instance, raw=False, **kwargs):
    if not raw:
        instance._billing_old = _snapshot(sender, instance, STUDENT_FIELDS)


@receiver(post_save, sender=Student)
def student_post_save(sender, instance, created, raw=False, **kwargs):
    if raw or created:
        return
    changed = _changed(instance, STUDENT_FIELDS)
    if not changed:
        return
    today = timezone.localdate()
    if 'status' in changed:
        if instance.status == Student.Status.FROZEN:
            _open_pause(today, "O'quvchi muzlatilgan", student=instance)
        else:
            _close_pause(today, student=instance)
        if instance.status == Student.Status.LEFT:
            # Markazdan ketgan o'quvchi barcha guruhlardan chiqariladi — keyingi oylar hisoblanmaydi.
            for gs in GroupStudent.objects.filter(student=instance, is_active=True):
                gs.is_active = False
                gs.save()
    sync_student(instance)


# ------------------------------------------------------------------ GroupStudent (a'zolik)

@receiver(pre_save, sender=GroupStudent)
def membership_pre_save(sender, instance, raw=False, **kwargs):
    if raw:
        return
    old = _snapshot(sender, instance, MEMBERSHIP_FIELDS)
    instance._billing_old = old
    instance._rejoin_gap = None
    if old is None:
        return
    today = timezone.localdate()
    if old['is_active'] and not instance.is_active and not instance.left_at:
        instance.left_at = today
    elif not old['is_active'] and instance.is_active:
        # Guruhga qaytdi: chiqqan kundan bugungacha bo'lgan oraliq hisoblanmaydi.
        if old['left_at']:
            instance._rejoin_gap = (old['left_at'], today)
        instance.left_at = None


@receiver(post_save, sender=GroupStudent)
def membership_post_save(sender, instance, created, raw=False, **kwargs):
    if raw:
        return
    gap = getattr(instance, '_rejoin_gap', None)
    if gap and gap[0] < gap[1]:
        pause = BillingPause(
            student_id=instance.student_id, group_id=instance.group_id,
            start_date=gap[0], end_date=gap[1], reason="Guruhdan chiqib, qayta qo'shilgan",
        )
        pause._skip_sync = True
        pause.save()
    if created or _changed(instance, MEMBERSHIP_FIELDS):
        sync_pair(instance.student, instance.group)


@receiver(post_save, sender=BillingPause)
@receiver(post_delete, sender=BillingPause)
def pause_changed(sender, instance, raw=False, **kwargs):
    # Django admin orqali qo'lda kiritilgan pauzalar ham darhol hisobga olinadi.
    if raw or getattr(instance, '_skip_sync', False):
        return
    origin = kwargs.get('origin')
    if origin is not None and not isinstance(origin, BillingPause) and getattr(origin, 'model', None) is not BillingPause:
        return  # o'quvchi/guruh o'chirilayotganda kaskad bilan o'chdi — qayta hisoblash shart emas
    if instance.student_id and instance.group_id:
        sync_pair(instance.student, instance.group)
    elif instance.student_id:
        sync_student(instance.student)
    elif instance.group_id:
        sync_group(instance.group)


# ------------------------------------------------------------------ To'lovlar (Django admin orqali tahrir)

@receiver(pre_save, sender=PaymentTransaction)
def payment_pre_save(sender, instance, raw=False, **kwargs):
    if not raw and instance.pk:
        instance._billing_old = sender.objects.filter(pk=instance.pk).values('student_id', 'group_id').first()


@receiver(post_save, sender=PaymentTransaction)
@receiver(post_delete, sender=PaymentTransaction)
def payment_changed(sender, instance, raw=False, **kwargs):
    # apply_payment/delete_payment o'zlari sync qiladi; bu yerda admin/shell dagi tahrirlar ushlanadi.
    if raw or getattr(instance, '_skip_sync', False):
        return
    origin = kwargs.get('origin')
    if origin is not None and not isinstance(origin, PaymentTransaction) and getattr(origin, 'model', None) is not PaymentTransaction:
        return
    pairs = {(instance.student_id, instance.group_id)}
    old = getattr(instance, '_billing_old', None)
    if old:
        pairs.add((old['student_id'], old['group_id']))
    for student_id, group_id in pairs:
        student = Student.objects.filter(pk=student_id).first()
        group = Group.objects.filter(pk=group_id).first()
        if student and group:
            sync_pair(student, group)
