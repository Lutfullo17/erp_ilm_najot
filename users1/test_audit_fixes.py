"""Audit (AUDIT_REPORT.md) topilmalari uchun regressiya testlari."""
import datetime
import json
from decimal import Decimal
from unittest import mock

from django.test import Client, TestCase, override_settings
from django.utils import timezone

from attendance.models import AttendanceRecord, AttendanceSession, LessonPlan
from grades.models import GradeRecord
from groups_app.models import Group, GroupStudent
from payments.models import PaymentTransaction
from students.models import Student
from users1.models import User

TEST_STORAGES = {
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
}
DAYS = ['Dushanba', 'Seshanba', 'Chorshanba', 'Payshanba', 'Juma', 'Shanba', 'Yakshanba']


def mk_user(name, role, **kw):
    user = User(username=name, role=role, **kw)
    user.set_password('pw-12345')
    user.save()
    return user


@override_settings(STORAGES=TEST_STORAGES)
class AuditBase(TestCase):
    def setUp(self):
        self.director = mk_user('dir', 'DIRECTOR')
        self.admin = mk_user('adm', 'ADMINISTRATOR')
        self.t1 = mk_user('t1', 'TEACHER')
        self.t2 = mk_user('t2', 'TEACHER')
        today = timezone.localdate()
        self.today = today
        self.g1 = Group.objects.create(
            name='G1', monthly_fee=Decimal('100000'), teacher=self.t1,
            start_date=today - datetime.timedelta(days=40),
            lesson_days=DAYS[today.weekday()], lesson_time=datetime.time(0, 0),
            end_time=datetime.time(23, 59), duration=Decimal('1'))
        self.g2 = Group.objects.create(
            name='G2', monthly_fee=Decimal('100000'), teacher=self.t2,
            start_date=today - datetime.timedelta(days=40))
        self.s1 = Student.objects.create(first_name='Ali', last_name='Valiyev')
        self.s_other = Student.objects.create(first_name='Boshqa', last_name='Guruh')
        GroupStudent.objects.create(group=self.g1, student=self.s1)
        GroupStudent.objects.create(group=self.g2, student=self.s_other)

    def login(self, user):
        client = Client()
        client.login(username=user.username, password='pw-12345')
        return client

    def jpost(self, client, url, data):
        return client.post(url, json.dumps(data), content_type='application/json')


class PermissionTests(AuditBase):
    def test_teacher_cannot_delete_teacher(self):  # K-1
        t3 = mk_user('t3', 'TEACHER')
        self.login(self.t1).post('/users/teachers/%d/delete/' % t3.pk)
        t3.refresh_from_db()
        self.assertFalse(t3.is_deleted)

    def test_director_can_delete_teacher(self):
        t3 = mk_user('t3', 'TEACHER')
        self.login(self.director).post('/users/teachers/%d/delete/' % t3.pk)
        t3.refresh_from_db()
        self.assertTrue(t3.is_deleted)

    def test_blocked_admin_session_is_terminated(self):  # Y-2
        client = self.login(self.admin)
        self.admin.is_blocked = True
        self.admin.save()
        r = self.jpost(client, '/payments/api/create/',
                       {'student_id': self.s1.pk, 'group_id': self.g1.pk, 'amount': 100000})
        self.assertNotEqual(r.status_code, 201)
        self.assertEqual(PaymentTransaction.objects.count(), 0)

    def test_blocked_teacher_cannot_mark_attendance(self):  # Y-2
        client = self.login(self.t1)
        self.t1.is_blocked = True
        self.t1.save()
        client.post('/attendance/mark/%d/' % self.g1.pk, {'status_%d' % self.s1.pk: 'PRESENT'})
        self.assertEqual(AttendanceRecord.objects.count(), 0)

    def test_teacher_cannot_write_foreign_lesson_plan(self):  # Y-4
        r = self.jpost(self.login(self.t1), '/attendance/api/save-lesson-plan/',
                       {'group_id': self.g2.pk, 'date': str(self.today), 'topic': 'HACK'})
        self.assertEqual(r.status_code, 403)
        self.assertFalse(LessonPlan.objects.exists())

    def test_teacher_can_write_own_lesson_plan(self):
        r = self.jpost(self.login(self.t1), '/attendance/api/save-lesson-plan/',
                       {'group_id': self.g1.pk, 'date': str(self.today), 'topic': 'OK'})
        self.assertEqual(r.status_code, 200)
