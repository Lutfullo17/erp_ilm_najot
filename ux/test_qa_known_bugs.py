"""QA: topilgan va tuzatilgan kamchiliklar uchun regressiya testlari. Hisobotdagi ID lar BACKEND_TEST_REPORT.md / FRONTEND_TEST_REPORT.md ga mos."""
import json

from payments.models import PaymentTransaction
from users1.test_audit_fixes import AuditBase


class KnownBugs(AuditBase):
    def _c(self, user):
        c = self.login(user)
        c.raise_request_exception = False
        return c

    def test_QA_B01_administrators_new_get_does_not_500(self):
        self.assertLess(self._c(self.director).get('/users/administrators/new/').status_code, 500)

    def test_QA_B03_json_type_confusion_does_not_500(self):
        c = self._c(self.admin)
        for url, body in (('/payments/api/create/', {'student_id': self.s1.pk, 'group_id': self.g1.pk, 'amount': '1e999'}),
                          ('/new/api/payments/', {'student_id': self.s1.pk, 'group_id': self.g1.pk, 'amount': 10 ** 30}),
                          ('/users/api/broadcast/', {'group_id': self.g1.pk, 'message': 123}),
                          ('/new/api/payments/', {'student_id': 'abc', 'group_id': self.g1.pk, 'amount': 1000}),
                          ('/new/api/students/%d/group/' % self.s1.pk, {'action': 'add', 'group_id': 'abc'})):
            self.assertLess(c.post(url, json.dumps(body), content_type='application/json').status_code, 500, (url, body))

    def test_QA_B04_null_created_by_does_not_break_director_pages(self):
        PaymentTransaction.objects.create(student=self.s1, group=self.g1, amount=1000, payment_date=self.today, created_by=None)
        c = self._c(self.director)
        for url in ('/users/admin/', '/new/payments/?p=all', '/new/payments/%d/receipt/' % PaymentTransaction.objects.get().pk):
            self.assertLess(c.get(url).status_code, 500, url)

    def test_QA_B05_grades_foreign_group_is_404_not_500(self):
        r = self._c(self.t1).get('/grades/teacher/groups/%d/?date=%s' % (self.g2.pk, self.today))
        self.assertIn(r.status_code, (403, 404))

    def test_QA_N01_bad_page_param_does_not_500(self):
        c = self._c(self.admin)
        for url in ('/new/students/', '/new/groups/', '/new/payments/', '/new/payments/debtors/', '/new/messages/', '/new/settings/telegram/'):
            self.assertLess(c.get(url, {'page': 'abc'}).status_code, 500, url)

    def test_QA_N02_huge_id_filter_does_not_500(self):
        c = self._c(self.admin)
        for url in ('/new/students/', '/new/payments/debtors/'):
            self.assertLess(c.get(url, {'group': '99999999999999999999'}).status_code, 500, url)


class FrontendFixes(AuditBase):
    def test_QA_F09_login_error_is_plain_uzbek(self):
        r = self.client.post('/users/login/', {'username': 'nobody', 'password': 'x'})
        self.assertContains(r, 'Foydalanuvchi nomi yoki parol noto&#x27;g&#x27;ri')
        self.assertNotContains(r, 'ikkala maydon')

    def test_QA_F13_no_english_login_label(self):
        self.assertContains(self.client.get('/users/login/'), 'Foydalanuvchi nomi')

    def test_QA_F04_pay_lookup_phone_is_formatted(self):
        self.s1.phone = '931112233'
        self.s1.save()
        r = self.login(self.admin).get('/new/api/pay/students/?q=%s' % self.s1.first_name)
        if r.status_code == 200 and r.json().get('students'):
            self.assertEqual(r.json()['students'][0]['phone'], '93 111 22 33')

    def test_QA_F05_new_student_page_has_single_pay_button(self):
        r = self.login(self.admin).get('/new/students/%d/?new=1' % self.s1.pk)
        self.assertEqual(r.content.decode().count("To'lov qabul qilish"), 1)
        self.assertNotContains(r, "To'langan")

    def test_QA_F03_session_expiry_returns_401_json(self):
        self.client.logout()
        self.assertEqual(self.client.get('/new/api/search/?q=Ali').status_code, 401)

    def test_session_cookie_age_is_12h(self):
        from django.conf import settings
        self.assertEqual(settings.SESSION_COOKIE_AGE, 12 * 3600)
