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
    def test_typed_phone_formats_are_accepted_but_do_not_verify_until_own_contact(self):  # K-2
        from bot.models import TelegramUser
        with mock.patch('bot.services.send_telegram_message'):
            for uid, typed in ((777, '901112233'), (778, '998901112233'), (779, '+998 90 111 22 33')):
                c = Client()
                self._update(c, '/start', uid=uid)
                self._update(c, typed, uid=uid)
                tg_user = TelegramUser.objects.get(telegram_id=uid)
                self.assertEqual(tg_user.phone, '998901112233')
                self.assertFalse(tg_user.is_verified)
                self.assertEqual(tg_user.state, 'WAITING_PHONE')
                self._update(c, contact={'phone_number': '+998901112233', 'user_id': uid}, uid=uid)
                tg_user.refresh_from_db()
                self.assertTrue(tg_user.is_verified)
                self.assertEqual(tg_user.student, self.s1)

    @override_settings(TELEGRAM_WEBHOOK_SECRET='s3cret')
    def test_typed_phone_requires_matching_telegram_contact(self):
        from bot.models import TelegramUser
        with mock.patch('bot.services.send_telegram_message'):
            c = Client()
            self._update(c, '/start')
            self._update(c, '901112233')
            self._update(c, contact={'phone_number': '+998901234567', 'user_id': 777})
        tg_user = TelegramUser.objects.get(telegram_id=777)
        self.assertFalse(tg_user.is_verified)
        self.assertIsNone(tg_user.student)

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


class MembershipTests(AuditBase):
    EDIT = {'full_name': 'Ali Valiyev', 'phone': '901234567', 'gender': 'MALE', 'status': 'ACTIVE',
            'discount_type': 'PERCENTAGE', 'discount_value': '0'}

    def _active(self):
        return sorted(GroupStudent.objects.filter(student=self.s1, is_active=True).values_list('group__name', flat=True))

    def test_editing_multi_group_student_keeps_memberships(self):  # Y-7
        GroupStudent.objects.create(group=self.g2, student=self.s1)
        self.login(self.admin).post('/students/%d/edit/' % self.s1.pk, dict(self.EDIT, group=self.g1.pk))
        self.assertEqual(self._active(), ['G1', 'G2'])

    def test_editing_single_group_student_can_transfer(self):
        self.login(self.admin).post('/students/%d/edit/' % self.s1.pk, dict(self.EDIT, group=self.g2.pk))
        self.assertEqual(self._active(), ['G2'])

    def test_cannot_add_deleted_or_left_student(self):  # O-12
        self.s_other.status = Student.Status.LEFT
        self.s_other.save()
        self.login(self.admin).post('/groups/%d/add-student/' % self.g1.pk, {'student_id': self.s_other.pk})
        self.assertFalse(GroupStudent.objects.filter(group=self.g1, student=self.s_other).exists())

    def test_cannot_add_to_inactive_group(self):
        self.g1.is_active = False
        self.g1.save()
        s3 = Student.objects.create(first_name='N', last_name='M')
        self.login(self.admin).post('/groups/%d/add-student/' % self.g1.pk, {'student_id': s3.pk})
        self.assertFalse(GroupStudent.objects.filter(group=self.g1, student=s3).exists())

    def test_remove_student_endpoint(self):
        self.login(self.admin).post('/groups/%d/remove-student/%d/' % (self.g1.pk, self.s1.pk))
        gs = GroupStudent.objects.get(group=self.g1, student=self.s1)
        self.assertFalse(gs.is_active)
        self.assertIsNotNone(gs.left_at)

    def test_group_list_counts_only_active_members(self):  # O-2
        s3 = Student.objects.create(first_name='N', last_name='M')
        GroupStudent.objects.create(group=self.g1, student=s3, is_active=False)
        r = self.login(self.admin).get('/groups/')
        g1 = [g for g in r.context['groups'] if g.pk == self.g1.pk][0]
        self.assertEqual(g1.active_students, 1)


class PenaltyScheduleTests(AuditBase):
    def _run_check(self):
        from users1 import penalty_service as ps
        now = timezone.make_aware(datetime.datetime.combine(self.today, datetime.time(23, 55)))
        self.g1.end_time = datetime.time(10, 0)
        self.g1.save()
        with mock.patch.object(ps.timezone, 'localtime', return_value=now), \
                mock.patch.object(ps, '_send_telegram_message', return_value=None):
            return ps.check_and_create_missed_alerts()

    def test_active_group_is_penalised(self):
        self.assertEqual(self._run_check()['penalties_applied'], 1)

    def test_paused_group_not_penalised(self):  # Y-12
        self.g1.is_paused = True
        self.g1.save()
        self.assertEqual(self._run_check()['penalties_applied'], 0)

    def test_not_yet_started_group_not_penalised(self):  # Y-12
        self.g1.start_date = self.today + datetime.timedelta(days=3)
        self.g1.save()
        self.assertEqual(self._run_check()['penalties_applied'], 0)

    def test_consecutive_chain_breaks_on_successful_lesson(self):  # O-11
        from users1.models import MissedAttendanceAlert
        from users1.penalty_service import get_teacher_consecutive_missed_count
        for i, d in enumerate([10, 8, 6, 2]):
            MissedAttendanceAlert.objects.create(
                teacher=self.t1, group=self.g1, lesson_date=self.today - datetime.timedelta(days=d),
                status='NOT_CAME', penalty_applied=True)
        # 7-kuni muvaffaqiyatli dars bo'lgan: zanjir 6-kundan keyin uziladi
        AttendanceSession.objects.create(group=self.g1, teacher=self.t1, date=self.today - datetime.timedelta(days=7))
        self.assertEqual(get_teacher_consecutive_missed_count(self.t1), 2)

    def test_schedule_notification_reaches_parents(self):  # Y-13
        from bot.models import TelegramUser
        from users1 import services
        from users1.models import ScheduleChangeRequest
        TelegramUser.objects.create(telegram_id=5, student=self.s1, is_verified=True)
        req = ScheduleChangeRequest.objects.create(
            teacher=self.t1, group=self.g1, old_day='Dushanba', old_start_time=datetime.time(9),
            old_end_time=datetime.time(10), new_day='Juma', new_start_time=datetime.time(9),
            new_end_time=datetime.time(10), reason='x')
        with mock.patch('bot.services.send_telegram_message', return_value={'ok': True}) as sm:
            services.send_schedule_change_notifications(req)
        self.assertEqual(sm.call_count, 1)

    def test_admin_edit_lesson_without_teacher_is_400_not_500(self):  # O-3
        self.g1.teacher = None
        self.g1.save()
        r = self.jpost(self.login(self.admin),
                       '/groups/%d/edit-lesson/%s/save/' % (self.g1.pk, DAYS[self.today.weekday()]),
                       {'start_time': '09:00', 'reason': 'x'})
        self.assertEqual(r.status_code, 400)

    def test_teacher_can_request_time_change_on_same_day(self):  # O-3
        from users1.views import ScheduleChangeRequestForm
        day = DAYS[self.today.weekday()]
        form = ScheduleChangeRequestForm(
            {'new_day': day, 'new_start_time': '14:00', 'reason': 'x'}, group=self.g1, teacher=self.t1,
            old_day=day, old_start_time=datetime.time(0, 0), old_end_time=datetime.time(23, 59))
        self.assertTrue(form.is_valid(), form.errors)


class HardeningTests(AuditBase):
    def _png(self):
        import io
        from PIL import Image
        buf = io.BytesIO()
        Image.new('RGB', (4, 4), 'red').save(buf, 'PNG')
        return buf.getvalue()

    def test_profile_photo_rejects_non_image(self):  # Y-10
        import tempfile
        from django.core.files.uploadedfile import SimpleUploadedFile
        with tempfile.TemporaryDirectory() as d, override_settings(MEDIA_ROOT=d):
            f = SimpleUploadedFile('evil.html', b'<script>alert(1)</script>', content_type='text/html')
            r = self.login(self.director).post('/users/admin/profile/change-photo/', {'photo': f})
        self.assertEqual(r.status_code, 400)

    def test_profile_photo_accepts_real_png_with_random_name(self):  # Y-10
        import tempfile
        from django.core.files.uploadedfile import SimpleUploadedFile
        with tempfile.TemporaryDirectory() as d, override_settings(MEDIA_ROOT=d):
            f = SimpleUploadedFile('../../x.html', self._png(), content_type='image/png')
            r = self.login(self.director).post('/users/admin/profile/change-photo/', {'photo': f})
            self.assertEqual(r.status_code, 200)
            self.assertTrue(r.json()['photo_url'].endswith('.png'))
            self.assertNotIn('x.html', r.json()['photo_url'])

    def test_weak_password_rejected_on_reset(self):  # O-7
        r = self.jpost(self.login(self.director), '/users/teachers/%d/reset-password/' % self.t1.pk,
                       {'new_password': '123456'})
        self.assertEqual(r.status_code, 400)

    def test_strong_password_accepted_on_reset(self):
        r = self.jpost(self.login(self.director), '/users/teachers/%d/reset-password/' % self.t1.pk,
                       {'new_password': 'Qiyin-Parol-2026!'})
        self.assertEqual(r.status_code, 200)

    def test_login_locks_after_repeated_failures(self):  # O-7
        from django.core.cache import cache
        cache.clear()
        c = Client()
        for _ in range(5):
            c.post('/users/login/', {'username': 't1', 'password': 'wrong'})
        r = c.post('/users/login/', {'username': 't1', 'password': 'pw-12345'})
        self.assertNotIn('_auth_user_id', c.session)
        cache.clear()

    def test_correct_login_still_works(self):
        from django.core.cache import cache
        cache.clear()
        c = Client()
        c.post('/users/login/', {'username': 't1', 'password': 'pw-12345'})
        self.assertIn('_auth_user_id', c.session)

    @override_settings(TRUST_X_FORWARDED_FOR=False)
    def test_client_ip_ignores_spoofed_forwarded_header(self):  # O-7
        from django.test import RequestFactory
        from users1.security import get_client_ip
        req = RequestFactory().get('/', HTTP_X_FORWARDED_FOR='6.6.6.6', REMOTE_ADDR='10.0.0.1')
        self.assertEqual(get_client_ip(req), '10.0.0.1')

    def test_payment_form_escapes_names(self):  # Y-14
        html = open('templates/payments/payment_form.html', encoding='utf-8').read()
        self.assertIn('esc(s.full_name)', html)
        self.assertNotIn('${s.full_name}', html)
        self.assertNotIn('${g.name}', html)
        self.assertNotIn('${d.name}', html)


class RobustnessTests(AuditBase):
    def test_payment_api_does_not_leak_internal_errors(self):  # O-5
        with mock.patch('payments.views.apply_payment', side_effect=RuntimeError('SECRET INTERNAL')):
            r = self.jpost(self.login(self.admin), '/payments/api/create/',
                           {'student_id': self.s1.pk, 'group_id': self.g1.pk, 'amount': 1000})
        self.assertEqual(r.status_code, 500)
        self.assertNotIn('SECRET INTERNAL', r.content.decode())

    def test_payment_input_error_is_400(self):
        r = self.jpost(self.login(self.admin), '/payments/api/create/',
                       {'student_id': self.s1.pk, 'group_id': self.g1.pk, 'amount': -5})
        self.assertEqual(r.status_code, 400)

    def test_absent_notification_not_resent_on_resave(self):  # O-4
        from attendance.models import AttendanceRecord
        s = AttendanceSession.objects.create(group=self.g1, teacher=self.t1, date=self.today)
        with mock.patch('attendance.signals.transaction.on_commit', side_effect=lambda f: f()), \
                mock.patch('bot.notifications.notify_attendance_absent') as notify:
            rec = AttendanceRecord.objects.create(session=s, student=self.s1, status='ABSENT')
            rec.comment = 'x'
            rec.save()
            AttendanceRecord.objects.update_or_create(session=s, student=self.s1, defaults={'status': 'ABSENT'})
        self.assertEqual(notify.call_count, 1)

    def test_broadcast_text_is_html_escaped(self):  # O-4
        from bot.models import TelegramUser
        TelegramUser.objects.create(telegram_id=9, student=self.s1, is_verified=True, phone='998901112233')
        with mock.patch('bot.broadcast.execute_broadcast') as ex:
            ex.return_value = mock.Mock(total=0, success=0, blocked=0, total_failed=0,
                                        failed_network=0, failed_api=0, failed_other=0)
            self.jpost(self.login(self.director), '/users/api/broadcast-all/', {'message': '<b>x</b> & y'})
        self.assertIn('&lt;b&gt;x&lt;/b&gt; &amp; y', ex.call_args[0][1])

    def test_student_discount_change_is_audited(self):  # O-16
        from users1.models import AuditLog
        self.login(self.admin).post('/students/%d/edit/' % self.s1.pk, {
            'full_name': 'Ali Valiyev', 'gender': 'MALE', 'status': 'ACTIVE', 'has_discount': 'on',
            'discount_type': 'PERCENTAGE', 'discount_value': '10', 'group': self.g1.pk})
        log = AuditLog.objects.get(action__startswith="O'quvchi holati/chegirmasi")
        self.assertEqual(Decimal(log.new_data['discount_value']), Decimal('10'))

    def test_report_month_out_of_range_does_not_crash(self):  # P-4
        r = self.login(self.director).get('/reports/finance/?month=9999-12')
        self.assertEqual(r.status_code, 200)

    def test_teacher_schedule_bad_week_offset_is_ok(self):  # O-1
        r = self.login(self.t1).get('/users/teacher/schedule/?week_offset=abc')
        self.assertEqual(r.status_code, 200)
