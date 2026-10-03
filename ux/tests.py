import json
from decimal import Decimal

from django.test import override_settings

from payments.models import PaymentTransaction
from users1.test_audit_fixes import AuditBase


class NewUiBase(AuditBase):
    def get(self, user, url, **kw):
        return self.login(user).get(url, **kw)


class HomeAndSwitchTests(NewUiBase):
    def test_home_for_each_role(self):
        for user in (self.admin, self.director, self.t1):
            r = self.get(user, '/new/')
            self.assertEqual(r.status_code, 200, user.username)
            self.assertContains(r, 'Assalomu alaykum')

    def test_anonymous_redirected_to_login(self):
        r = self.client.get('/new/')
        self.assertEqual(r.status_code, 302)
        self.assertIn('/users/login/', r['Location'])

    def test_switch_sets_cookie_and_login_redirects(self):
        c = self.login(self.admin)
        r = c.get('/new/switch/new/')
        self.assertEqual(r.cookies['ui'].value, 'new')
        r = c.get('/users/')
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r['Location'], '/new/')
        c.get('/new/switch/old/')
        self.assertEqual(c.get('/users/')['Location'], '/users/administrator/')

    @override_settings(NEW_UI_USERS=['adm'])
    def test_flag_enables_new_ui_only_for_listed_users(self):
        self.assertEqual(self.login(self.admin).get('/users/')['Location'], '/new/')
        self.assertNotEqual(self.login(self.director).get('/users/')['Location'], '/new/')

    def test_old_ui_unchanged_by_default(self):
        self.assertEqual(self.login(self.admin).get('/users/')['Location'], '/users/administrator/')

    def test_teacher_cannot_open_admin_pages(self):
        for url in ('/new/payments/new/', '/new/payments/debtors/', '/new/payments/'):
            r = self.get(self.t1, url)
            self.assertEqual(r.status_code, 302, url)
            self.assertEqual(r['Location'], '/new/')

    def test_search_requires_login_and_finds_student(self):
        self.assertEqual(self.client.get('/new/api/search/?q=Ali').status_code, 401)
        r = self.get(self.admin, '/new/api/search/?q=Ali')
        self.assertEqual(r.json()['groups'][0]['items'][0]['title'], 'Ali Valiyev')

    def test_feedback_saved(self):
        from ux.models import Feedback
        r = self.login(self.admin).post('/new/feedback/', json.dumps({'message': 'Tushunmadim', 'page': '/new/'}),
                                        content_type='application/json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Feedback.objects.get().message, 'Tushunmadim')


class NewPaymentTests(NewUiBase):
    def _pay(self, user, **extra):
        body = {'student_id': self.s1.pk, 'group_id': self.g1.pk, 'amount': 100000, 'method': 'CASH'}
        body.update(extra)
        return self.jpost(self.login(user), '/new/api/payments/', body)

    def test_pay_page_renders(self):
        r = self.get(self.admin, '/new/payments/new/')
        self.assertContains(r, 'Qancha qabul qilasiz')
        r = self.get(self.admin, '/new/payments/new/?student=%d' % self.s1.pk)
        self.assertContains(r, 'preData')

    def test_pay_info_has_groups_and_debt(self):
        d = self.get(self.admin, '/new/api/pay-info/%d/' % self.s1.pk).json()
        self.assertEqual(d['groups'][0]['id'], self.g1.pk)

    def test_create_and_idempotent(self):
        key = '3f2b8a52-6a3e-4b7c-9d5e-0c1d2e3f4a5b'
        r1 = self._pay(self.admin, idempotency_key=key)
        r2 = self._pay(self.admin, idempotency_key=key)
        self.assertEqual((r1.status_code, r2.status_code), (201, 200))
        self.assertEqual(PaymentTransaction.objects.count(), 1)
        self.assertIn('receipt_url', r1.json()['payment'])

    def test_validation_errors_are_400_in_uzbek(self):
        for amount in (0, -5, 'abc', 10 ** 12):
            r = self._pay(self.admin, amount=amount)
            self.assertEqual(r.status_code, 400, amount)
            self.assertTrue(r.json()['detail'])

    def test_teacher_cannot_pay(self):
        self.assertEqual(self._pay(self.t1).status_code, 403)

    def test_admin_undo_own_payment_within_window(self):
        r = self._pay(self.admin)
        undo = r.json()['payment']['undo_url']
        r2 = self.login(self.admin).post(undo, '{}', content_type='application/json')
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(PaymentTransaction.objects.count(), 0)

    def test_admin_cannot_undo_old_or_foreign_payment(self):
        from datetime import timedelta
        from django.utils import timezone
        p = PaymentTransaction.objects.get(pk=self._pay(self.admin).json()['payment']['id'])
        PaymentTransaction.objects.filter(pk=p.pk).update(created_at=timezone.now() - timedelta(minutes=10))
        r = self.login(self.admin).post('/new/api/payments/%d/undo/' % p.pk, '{}', content_type='application/json')
        self.assertEqual(r.status_code, 403)
        p2 = PaymentTransaction.objects.get(pk=self._pay(self.director, amount=5000).json()['payment']['id'])
        r = self.login(self.admin).post('/new/api/payments/%d/undo/' % p2.pk, '{}', content_type='application/json')
        self.assertEqual(r.status_code, 403)

    def test_history_debtors_receipt(self):
        pid = self._pay(self.admin).json()['payment']['id']
        self.assertContains(self.get(self.admin, '/new/payments/?p=all'), 'Ali Valiyev')
        self.assertEqual(self.get(self.admin, '/new/payments/debtors/').status_code, 200)
        self.assertContains(self.get(self.admin, '/new/payments/%d/receipt/' % pid), 'Kvitansiya')
        self.assertEqual(self.get(self.director, '/new/payments/%d/receipt/' % pid).status_code, 200)

    def test_receipt_of_foreign_payment_404_for_other_admin(self):
        from ux.nav import role_of  # noqa: F401
        from users1.test_audit_fixes import mk_user
        other = mk_user('adm2', 'ADMINISTRATOR')
        pid = self._pay(self.admin).json()['payment']['id']
        self.assertEqual(self.get(other, '/new/payments/%d/receipt/' % pid).status_code, 404)

    def test_director_delete_via_new_ui(self):
        pid = self._pay(self.admin).json()['payment']['id']
        self.login(self.director).post('/new/payments/%d/delete/' % pid)
        self.assertEqual(PaymentTransaction.objects.count(), 0)
