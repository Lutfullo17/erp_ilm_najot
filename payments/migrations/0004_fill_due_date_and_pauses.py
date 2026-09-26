from calendar import monthrange

from django.db import migrations
from django.utils import timezone


def forwards(apps, schema_editor):
    StudentMonthBalance = apps.get_model('payments', 'StudentMonthBalance')
    BillingPause = apps.get_model('payments', 'BillingPause')
    Student = apps.get_model('students', 'Student')
    Group = apps.get_model('groups_app', 'Group')

    # 1. Har bir balans uchun to'lov muddati (guruh boshlangan kun bo'yicha)
    for balance in StudentMonthBalance.objects.select_related('group').iterator():
        month = balance.month.replace(day=1)
        start = balance.group.start_date
        due = month.replace(day=min(start.day, monthrange(month.year, month.month)[1])) if start else month
        StudentMonthBalance.objects.filter(pk=balance.pk).update(due_date=due)

    # 2. Hozir muzlatilgan o'quvchilar va to'xtatilgan guruhlar uchun ochiq pauza
    #    (qachon boshlangani noma'lum — bugundan boshlab hisoblanmaydi).
    today = timezone.localdate()
    for student in Student.objects.filter(status='FROZEN'):
        BillingPause.objects.create(student=student, start_date=today, reason="O'quvchi muzlatilgan (migratsiya)")
    for group in Group.objects.filter(is_paused=True):
        BillingPause.objects.create(group=group, start_date=today, reason="Guruh to'xtatilgan (migratsiya)")


class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0003_due_date_billingpause'),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
