"""Audit dalillari: test o'tsa == kamchilik mavjud (xulq-atvor tasdiqlandi)."""
import datetime
import json
import tempfile
from decimal import Decimal
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, Client, override_settings
from django.utils import timezone

from users1.models import User
from students.models import Student
from groups_app.models import Group, GroupStudent
from attendance.models import AttendanceRecord, AttendanceSession, LessonPlan
from grades.models import GradeRecord
from payments.models import PaymentTransaction

STORAGES = {
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
}
DAYS = ['Dushanba', 'Seshanba', 'Chorshanba', 'Payshanba', 'Juma', 'Shanba', 'Yakshanba']


def mk_user(name, role, **kw):
    u = User(username=name, role=role, **kw)
    u.set_password('pw-12345')
    u.save()
    return u


@override_settings(STORAGES=STORAGES, ALLOWED_HOSTS=['testserver'])
class Proof(TestCase):
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
        c = Client()
        c.login(username=user.username, password='pw-12345')
        return c

    def jpost(self, c, url, data):
        return c.post(url, json.dumps(data), content_type='application/json')

    def test_teacher_can_delete_another_teacher(self):
        t3 = mk_user('t3', 'TEACHER')
        r = self.login(self.t1).post('/users/teachers/%d/delete/' % t3.pk)
        t3.refresh_from_db()
        print('\n[delete_teacher] status', r.status_code, 'is_deleted=', t3.is_deleted)
        self.assertTrue(t3.is_deleted)

    def test_teacher_marks_attendance_for_foreign_student_with_invalid_status(self):
        c = self.login(self.t1)
        c.post('/attendance/mark/%d/' % self.g1.pk, {
            'status_%d' % self.s_other.pk: 'ABSENT', 'status_%d' % self.s1.pk: 'GARBAGE'})
        recs = {x.student_id: x.status for x in AttendanceRecord.objects.all()}
        print('\n[attendance] records:', recs)
        self.assertIn(self.s_other.pk, recs)
        self.assertEqual(recs[self.s1.pk], 'GARBAGE')

    def test_teacher_overwrites_foreign_group_lesson_plan(self):
        c = self.login(self.t1)
        r = self.jpost(c, '/attendance/api/save-lesson-plan/',
                       {'group_id': self.g2.pk, 'date': str(self.today), 'topic': 'HACK'})
        print('\n[lesson_plan] status', r.status_code,
              list(LessonPlan.objects.filter(group=self.g2).values_list('topic', 'teacher__username')))
        self.assertEqual(r.status_code, 200)

    def test_admin_override_deletes_existing_attendance(self):
        s = AttendanceSession.objects.create(group=self.g1, teacher=self.t1, date=self.today)
        AttendanceRecord.objects.create(session=s, student=self.s1, status='PRESENT')
        self.jpost(self.login(self.admin), '/attendance/api/admin-override/%d/' % self.g1.pk,
                   {'date': str(self.today)})
        print('\n[override] records left:', AttendanceRecord.objects.count())
        self.assertEqual(AttendanceRecord.objects.count(), 0)

    def test_blank_grade_saved_as_zero(self):
        c = self.login(self.t1)
        c.post('/grades/input/', {'group_id': self.g1.pk, 'grade_date': str(self.today),
                                  'title': 'T', 'percentage_%d' % self.s1.pk: ''})
        rec = GradeRecord.objects.first()
        print('\n[grades] saved:', rec.percentage if rec else None)
        self.assertEqual(rec.percentage, Decimal('0.00'))

    def test_editing_student_removes_other_group_memberships(self):
        GroupStudent.objects.create(group=self.g2, student=self.s1)
        r = self.login(self.admin).post('/students/%d/edit/' % self.s1.pk, {
            'full_name': 'Ali Valiyev', 'phone': '901234567', 'gender': 'MALE', 'status': 'ACTIVE',
            'group': self.g1.pk, 'discount_type': 'PERCENTAGE', 'discount_value': '0'})
        active = list(GroupStudent.objects.filter(student=self.s1, is_active=True)
                      .values_list('group__name', flat=True))
        print('\n[student_edit] status', r.status_code, 'active groups:', active)
        self.assertEqual(active, ['G1'])

    def test_blocked_admin_can_still_take_payment(self):
        c = self.login(self.admin)
        self.admin.is_blocked = True
        self.admin.save()
        r = self.jpost(c, '/payments/api/create/',
                       {'student_id': self.s1.pk, 'group_id': self.g1.pk, 'amount': 100000})
        print('\n[blocked admin payment] status', r.status_code)
        self.assertEqual(r.status_code, 201)

    def test_duplicate_payment_request_creates_two_payments(self):
        c = self.login(self.admin)
        body = {'student_id': self.s1.pk, 'group_id': self.g1.pk, 'amount': 50000,
                'payment_date': str(self.today)}
        r1 = self.jpost(c, '/payments/api/create/', body)
        r2 = self.jpost(c, '/payments/api/create/', body)
        print('\n[dup payment]', r1.status_code, r2.status_code, PaymentTransaction.objects.count())
        self.assertEqual(PaymentTransaction.objects.count(), 2)

    def test_payment_can_be_backdated_arbitrarily(self):
        r = self.jpost(self.login(self.admin), '/payments/api/create/',
                       {'student_id': self.s1.pk, 'group_id': self.g1.pk, 'amount': 1000,
                        'payment_date': '2020-01-01'})
        print('\n[backdate]', r.status_code)
        self.assertEqual(r.status_code, 201)

    def test_teacher_schedule_bad_week_offset_is_500(self):
        c = self.login(self.t1)
        c.raise_request_exception = False
        r = c.get('/users/teacher/schedule/?week_offset=abc')
        print('\n[week_offset] status', r.status_code)
        self.assertEqual(r.status_code, 500)

    def test_profile_photo_accepts_non_image(self):
        with tempfile.TemporaryDirectory() as d, override_settings(MEDIA_ROOT=d):
            f = SimpleUploadedFile('evil.html', b'<script>alert(1)</script>', content_type='text/html')
            r = self.login(self.director).post('/users/admin/profile/change-photo/', {'photo': f})
            print('\n[photo] status', r.status_code, r.content[:120])
            self.assertEqual(r.status_code, 200)

    def test_paused_group_still_penalised(self):
        from users1 import penalty_service as ps
        self.g1.is_paused = True
        self.g1.end_time = datetime.time(10, 0)
        self.g1.save()
        now = timezone.make_aware(datetime.datetime.combine(self.today, datetime.time(23, 55)))
        with mock.patch.object(ps.timezone, 'localtime', return_value=now), \
                mock.patch.object(ps, '_send_telegram_message', return_value=None):
            res = ps.check_and_create_missed_alerts()
        print('\n[paused penalty]', res)
        self.assertEqual(res['penalties_applied'], 1)

    def test_bot_phone_text_verifies_without_ownership_proof(self):
        from bot import services
        from bot.models import TelegramUser
        self.s1.parent_phone = '+998901112233'
        self.s1.save()
        with override_settings(TELEGRAM_WEBHOOK_SECRET=''), \
                mock.patch.object(services, 'send_telegram_message'):
            c = Client()
            for text in ['/start', '901112233']:
                c.post('/bot/telegram/webhook/', json.dumps(
                    {'message': {'chat': {'id': 777}, 'from': {'id': 777, 'first_name': 'X'}, 'text': text}}),
                    content_type='application/json')
        tu = TelegramUser.objects.get(telegram_id=777)
        print('\n[bot] verified=', tu.is_verified, 'student=', tu.student)
        self.assertTrue(tu.is_verified)

    def test_blocked_teacher_can_still_mark_attendance(self):
        c = self.login(self.t1)
        self.t1.is_blocked = True
        self.t1.save()
        r = c.post('/attendance/mark/%d/' % self.g1.pk, {'status_%d' % self.s1.pk: 'PRESENT'})
        print('\n[blocked teacher attendance] records', AttendanceRecord.objects.count(), r.status_code)
        self.assertEqual(AttendanceRecord.objects.count(), 1)
