"""QA: XSS, IDOR (obyekt darajasida), sessiya/cookie, sarlavhalar, parol qoidalari."""
import datetime

from django.test import Client, override_settings

from attendance.models import AttendanceRecord, AttendanceSession
from bot.models import TelegramAppeal, TelegramUser
from groups_app.models import Group, GroupStudent
from payments.models import PaymentTransaction
from students.models import Student
from users1.models import User
from users1.test_audit_fixes import AuditBase, mk_user

XSS = '<script>alert("x")</script>'
IMG = '"><img src=x onerror=alert(1)>'


class StoredXssTests(AuditBase):
    """Foydalanuvchi kiritgan matn hamma ro'yxat/kartochkada escape qilinishi shart."""

    def _assert_escaped(self, response, url):
        body = response.content.decode()
        self.assertNotIn(XSS, body, url)
        self.assertNotIn('<img src=x onerror', body, url)

    def test_names_and_messages_escaped_everywhere(self):
        evil = Student.objects.create(first_name=XSS, last_name=IMG, phone='901234500', parent_phone='901234501')
        g = Group.objects.create(name=XSS + 'G', monthly_fee=1, teacher=self.t1, start_date=self.today - datetime.timedelta(days=40),
                                 lesson_days='Dushanba', lesson_time=datetime.time(10, 0), end_time=datetime.time(11, 0), room=1)
        GroupStudent.objects.create(group=g, student=evil, joined_at=self.today - datetime.timedelta(days=35))
        self.t1.first_name, self.t1.last_name = XSS, IMG
        self.t1.save()
        tu = TelegramUser.objects.create(telegram_id=1, student=evil, is_verified=True, phone='998901234501')
        TelegramAppeal.objects.create(telegram_user=tu, student=evil, message=XSS + IMG)
        from users1.models import AuditLog
        AuditLog.objects.create(user=self.admin, action=XSS, role='X')
        from ux.models import Feedback
        Feedback.objects.create(user=self.admin, message=XSS, page=IMG)
        pay = PaymentTransaction.objects.create(student=evil, group=g, amount=1000, payment_date=self.today, note=XSS, created_by=self.admin)
        urls = ['/new/students/?q=script', '/new/students/%d/' % evil.pk, '/new/students/%d/edit/' % evil.pk, '/new/groups/', '/new/groups/%d/' % g.pk,
                '/new/groups/%d/edit/' % g.pk, '/new/payments/?p=all', '/new/payments/%d/receipt/' % pay.pk, '/new/payments/debtors/',
                '/new/messages/?f=all', '/new/staff/', '/new/staff/teachers/%d/' % self.t1.pk, '/new/settings/', '/new/settings/log/',
                '/new/settings/telegram/', '/new/schedule/', '/new/attendance/', '/new/attendance/%d/' % g.pk, '/new/reports/',
                '/students/', '/groups/', '/payments/', '/users/teachers/', '/users/messages/']
        c = self.login(self.director)
        c.raise_request_exception = False
        for url in urls:
            r = c.get(url)
            self.assertLess(r.status_code, 500, url)
            self._assert_escaped(r, url)
        # JSON javoblarda '<' xom holda keladi (Content-Type: application/json + nosniff); front-end uni textContent bilan chizadi.
        self.assertEqual(c.get('/new/api/search/?q=script')['Content-Type'].split(';')[0], 'application/json')
        t = self.login(self.t1)
        for url in ('/new/', '/new/my-groups/', '/new/my-groups/%d/' % g.pk, '/new/attendance/%d/' % g.pk, '/new/profile/'):
            self._assert_escaped(t.get(url), url)

    def test_search_json_is_not_html_sniffable(self):
        r = self.get_admin('/new/api/search/?q=Ali')
        self.assertEqual(r['Content-Type'].split(';')[0], 'application/json')

    def get_admin(self, url):
        return self.login(self.admin).get(url)


class IdorTests(AuditBase):
    def test_teacher_cannot_touch_other_teachers_group_through_any_url(self):
        c = self.login(self.t1)
        c.raise_request_exception = False
        checks = [
            ('get', '/attendance/mark/%d/' % self.g2.pk), ('post', '/attendance/mark/%d/' % self.g2.pk),
            ('get', '/users/teacher/groups/%d/' % self.g2.pk), ('get', '/users/teacher/students/%d/' % self.s_other.pk),
            ('get', '/grades/teacher/groups/%d/?date=%s' % (self.g2.pk, self.today)),
            ('get', '/new/my-groups/%d/' % self.g2.pk), ('get', '/new/my-students/%d/' % self.s_other.pk),
            ('get', '/new/attendance/%d/' % self.g2.pk), ('get', '/users/teacher/groups/%d/schedule-change-request/' % self.g2.pk),
        ]
        for method, url in checks:
            r = getattr(c, method)(url)
            self.assertNotEqual(r.status_code, 200, url)
        self.assertEqual(AttendanceRecord.objects.count(), 0)

    def test_second_administrator_cannot_see_or_undo_first_ones_payment(self):
        import json
        other = mk_user('adm2', 'ADMINISTRATOR')
        c1 = self.login(self.admin)
        pid = c1.post('/new/api/payments/', json.dumps({'student_id': self.s1.pk, 'group_id': self.g1.pk, 'amount': 1000}),
                      content_type='application/json').json()['payment']['id']
        c2 = self.login(other)
        self.assertEqual(c2.get('/new/payments/%d/receipt/' % pid).status_code, 404)
        self.assertEqual(c2.post('/new/api/payments/%d/undo/' % pid, '{}', content_type='application/json').status_code, 403)
        self.assertNotContains(c2.get('/new/payments/?p=all'), 'Ali Valiyev')
        self.assertEqual(c2.post('/new/payments/%d/delete/' % pid).status_code, 302)
        self.assertTrue(PaymentTransaction.objects.filter(pk=pid).exists())

    def test_numeric_ids_cannot_be_enumerated_to_deleted_or_foreign_objects(self):
        deleted = Student.objects.create(first_name='Del', last_name='X', is_deleted=True, is_active=False)
        c = self.login(self.admin)
        c.raise_request_exception = False
        self.assertEqual(c.get('/new/students/%d/' % deleted.pk).status_code, 404)
        self.assertEqual(c.get('/new/students/%d/edit/' % deleted.pk).status_code, 404)
        self.assertEqual(c.get('/new/api/pay-info/%d/' % deleted.pk).status_code, 404)


class SessionAndHeaderTests(AuditBase):
    def test_security_headers_and_cookie_flags(self):
        c = Client()
        r = c.post('/users/login/', {'username': 't1', 'password': 'pw-12345'})
        cookie = r.cookies['sessionid']
        self.assertTrue(cookie['httponly'])
        self.assertEqual(cookie['samesite'], 'Lax')
        r = self.login(self.admin).get('/new/')
        self.assertEqual(r['X-Frame-Options'], 'DENY')
        self.assertEqual(r['X-Content-Type-Options'], 'nosniff')

    def test_login_error_does_not_reveal_whether_user_exists(self):
        from django.core.cache import cache
        cache.clear()
        a = Client().post('/users/login/', {'username': 't1', 'password': 'bad'}).content.decode()
        b = Client().post('/users/login/', {'username': 'no-such-user', 'password': 'bad'}).content.decode()
        import re
        strip = lambda s: re.sub(r'csrfmiddlewaretoken" value="[^"]+"|value="[^"]*"', '', s)
        self.assertEqual(strip(a), strip(b))
        cache.clear()

    def test_blocked_user_cannot_log_in(self):
        self.t1.is_blocked = True
        self.t1.save()
        c = Client()
        c.post('/users/login/', {'username': 't1', 'password': 'pw-12345'})
        self.assertNotIn('_auth_user_id', c.session)

    def test_deleted_teacher_cannot_log_in(self):
        self.t1.is_active, self.t1.is_deleted = False, True
        self.t1.save()
        c = Client()
        c.post('/users/login/', {'username': 't1', 'password': 'pw-12345'})
        self.assertNotIn('_auth_user_id', c.session)

    def test_password_validators_enforced_for_new_staff(self):
        c = self.login(self.director)
        for weak in ('12345678', 'password', 'abc'):   # 't1t1t1t1' (loginga o'xshash) — QA-B-09, parol-login o'xshashligi tekshirilmaydi
            r = c.post('/new/staff/teachers/new/', {'full_name': 'Yangi Ustoz', 'username': 'yu', 'password1': weak, 'password2': weak})
            self.assertEqual(r.status_code, 400, weak)
        self.assertFalse(User.objects.filter(username='yu').exists())

    @override_settings(DEBUG=False)
    def test_404_page_does_not_leak_internals(self):
        c = self.login(self.admin)
        r = c.get('/new/students/999999/')
        self.assertEqual(r.status_code, 404)
        self.assertNotIn('Traceback', r.content.decode())
        self.assertNotIn('settings', r.content.decode().lower().replace('sozlamalar', ''))

    def test_session_invalid_after_password_reset_by_director(self):
        c = self.login(self.t1)
        self.assertEqual(c.get('/new/').status_code, 200)
        self.login(self.director).post('/users/teachers/%d/reset-password/' % self.t1.pk, '{"new_password": "Yangi-Parol-2026!"}',
                                       content_type='application/json')
        # Django sessiya xeshi parol o'zgargach yaroqsiz bo'lishi kerak
        self.assertEqual(c.get('/new/').status_code, 302)
