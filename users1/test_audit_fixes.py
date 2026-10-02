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


class BotSecurityTests(AuditBase):
    def _update(self, client, text=None, contact=None, secret='s3cret', uid=777):
        message = {'chat': {'id': uid}, 'from': {'id': uid, 'first_name': 'X'}}
        if text is not None:
            message['text'] = text
        if contact is not None:
            message['contact'] = contact
        headers = {'HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN': secret} if secret else {}
        return client.post('/bot/telegram/webhook/', json.dumps({'message': message}),
                           content_type='application/json', **headers)

    def setUp(self):
        super().setUp()
        self.s1.parent_phone = '+998901112233'
        self.s1.save()

    @override_settings(TELEGRAM_WEBHOOK_SECRET='')
    def test_webhook_without_configured_secret_is_refused(self):  # K-2
        self.assertEqual(self._update(Client(), '/start', secret='').status_code, 503)

    @override_settings(TELEGRAM_WEBHOOK_SECRET='s3cret')
    def test_webhook_wrong_secret_forbidden(self):
        self.assertEqual(self._update(Client(), '/start', secret='bad').status_code, 403)

    @override_settings(TELEGRAM_WEBHOOK_SECRET='s3cret')
    def test_typed_phone_does_not_verify(self):  # K-2
        from bot.models import TelegramUser
        with mock.patch('bot.services.send_telegram_message'):
            c = Client()
            self._update(c, '/start')
            self._update(c, '901112233')
        self.assertFalse(TelegramUser.objects.get(telegram_id=777).is_verified)

    @override_settings(TELEGRAM_WEBHOOK_SECRET='s3cret')
    def test_foreign_contact_without_user_id_rejected(self):  # K-2
        from bot.models import TelegramUser
        with mock.patch('bot.services.send_telegram_message'):
            self._update(Client(), contact={'phone_number': '+998901112233'})
        self.assertFalse(TelegramUser.objects.get(telegram_id=777).is_verified)

    @override_settings(TELEGRAM_WEBHOOK_SECRET='s3cret')
    def test_own_contact_verifies(self):
        from bot.models import TelegramUser
        with mock.patch('bot.services.send_telegram_message'):
            self._update(Client(), contact={'phone_number': '+998901112233', 'user_id': 777})
        self.assertTrue(TelegramUser.objects.get(telegram_id=777).is_verified)

    @override_settings(TELEGRAM_WEBHOOK_SECRET='s3cret')
    def test_handler_exception_returns_200(self):  # O-6
        with mock.patch('bot.views.handle_update', side_effect=RuntimeError('boom')):
            self.assertEqual(self._update(Client(), '/start').status_code, 200)

    @override_settings(TELEGRAM_BOT_TOKEN='123:SECRETTOKEN')
    def test_scrub_removes_token(self):  # Y-11
        from bot.utils import scrub
        self.assertNotIn('SECRETTOKEN', scrub('url: /bot123:SECRETTOKEN/sendMessage'))


class AttendanceGradeTests(AuditBase):
    def test_attendance_rejects_foreign_student_and_bad_status(self):  # Y-3
        c = self.login(self.t1)
        c.post('/attendance/mark/%d/' % self.g1.pk, {'status_%d' % self.s_other.pk: 'ABSENT'})
        c.post('/attendance/mark/%d/' % self.g1.pk, {'status_%d' % self.s1.pk: 'GARBAGE'})
        self.assertEqual(AttendanceRecord.objects.count(), 0)

    def test_attendance_valid_saved(self):
        self.login(self.t1).post('/attendance/mark/%d/' % self.g1.pk, {'status_%d' % self.s1.pk: 'PRESENT'})
        self.assertEqual(AttendanceRecord.objects.get().status, 'PRESENT')

    def test_admin_override_keeps_snapshot_in_audit_log(self):  # Y-5
        from users1.models import AuditLog
        s = AttendanceSession.objects.create(group=self.g1, teacher=self.t1, date=self.today)
        AttendanceRecord.objects.create(session=s, student=self.s1, status='PRESENT')
        self.jpost(self.login(self.admin), '/attendance/api/admin-override/%d/' % self.g1.pk,
                   {'date': str(self.today)})
        log = AuditLog.objects.filter(action__startswith='Admin Override').get()
        self.assertEqual(log.old_data['records'][0]['status'], 'PRESENT')

    def test_blank_grade_is_not_saved_as_zero(self):  # Y-6
        s2 = Student.objects.create(first_name='Vali', last_name='X')
        GroupStudent.objects.create(group=self.g1, student=s2)
        self.login(self.t1).post('/grades/input/', {
            'group_id': self.g1.pk, 'grade_date': str(self.today), 'title': 'T',
            'percentage_%d' % self.s1.pk: '85', 'percentage_%d' % s2.pk: ''})
        recs = {r.student_id: r.percentage for r in GradeRecord.objects.all()}
        self.assertEqual(recs, {self.s1.pk: Decimal('85.00')})

    def test_grade_for_foreign_student_rejected(self):
        self.login(self.t1).post('/grades/input/', {
            'group_id': self.g1.pk, 'grade_date': str(self.today), 'title': 'T',
            'percentage_%d' % self.s_other.pk: '50'})
        self.assertFalse(GradeRecord.objects.exists())


class PaymentIntegrityTests(AuditBase):
    def _pay(self, user=None, **extra):
        body = {'student_id': self.s1.pk, 'group_id': self.g1.pk, 'amount': 50000,
                'payment_date': str(self.today)}
        body.update(extra)
        return self.jpost(self.login(user or self.admin), '/payments/api/create/', body)

    def test_same_idempotency_key_creates_one_payment(self):  # Y-8
        key = '3f2b8a52-6a3e-4b7c-9d5e-0c1d2e3f4a5b'
        r1, r2 = self._pay(idempotency_key=key), self._pay(idempotency_key=key)
        self.assertEqual((r1.status_code, r2.status_code), (201, 200))
        self.assertTrue(r2.json()['duplicate'])
        self.assertEqual(PaymentTransaction.objects.count(), 1)

    def test_identical_payment_without_key_rejected_within_a_minute(self):  # Y-8
        self._pay()
        self.assertEqual(self._pay().status_code, 400)
        self.assertEqual(PaymentTransaction.objects.count(), 1)

    def test_payment_create_and_delete_are_audited(self):  # Y-8 / O-16
        from users1.models import AuditLog
        r = self._pay()
        pid = r.json()['payment']['id']
        self.login(self.director).post('/payments/delete/%d/' % pid)
        self.assertTrue(AuditLog.objects.filter(action="To'lov qabul qilindi").exists())
        deleted = AuditLog.objects.get(action="To'lov o'chirildi")
        self.assertEqual(deleted.old_data['amount'], '50000.00')

    def test_admin_cannot_backdate_beyond_limit(self):  # Y-9
        old = str(self.today - datetime.timedelta(days=30))
        self.assertEqual(self._pay(payment_date=old).status_code, 400)

    def test_director_can_backdate(self):  # Y-9
        old = str(self.today - datetime.timedelta(days=30))
        self.assertEqual(self._pay(user=self.director, payment_date=old).status_code, 201)
