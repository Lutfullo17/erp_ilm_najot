"""QA: topilgan, hali tuzatilmagan kamchiliklar. Har biri `expectedFailure`: tuzatilgach test "kutilmagan muvaffaqiyat" beradi
va dekoratorni olib tashlash kerak (5-bosqich). Hisobotdagi ID lar BACKEND_TEST_REPORT.md / FRONTEND_TEST_REPORT.md ga mos."""
import json
import unittest

from payments.models import PaymentTransaction
from users1.test_audit_fixes import AuditBase


class KnownBugs(AuditBase):
    def _c(self, user):
        c = self.login(user)
        c.raise_request_exception = False
        return c

    @unittest.expectedFailure
    def test_QA_B01_administrators_new_get_does_not_500(self):
        self.assertLess(self._c(self.director).get('/users/administrators/new/').status_code, 500)

    @unittest.expectedFailure
    def test_QA_B03_json_type_confusion_does_not_500(self):
        c = self._c(self.admin)
        for url, body in (('/payments/api/create/', {'student_id': self.s1.pk, 'group_id': self.g1.pk, 'amount': '1e999'}),
                          ('/new/api/payments/', {'student_id': self.s1.pk, 'group_id': self.g1.pk, 'amount': 10 ** 30}),
                          ('/users/api/broadcast/', {'group_id': self.g1.pk, 'message': 123}),
                          ('/new/api/payments/', {'student_id': 'abc', 'group_id': self.g1.pk, 'amount': 1000}),
                          ('/new/api/students/%d/group/' % self.s1.pk, {'action': 'add', 'group_id': 'abc'})):
            self.assertLess(c.post(url, json.dumps(body), content_type='application/json').status_code, 500, (url, body))

    @unittest.expectedFailure
    def test_QA_B04_null_created_by_does_not_break_director_pages(self):
        PaymentTransaction.objects.create(student=self.s1, group=self.g1, amount=1000, payment_date=self.today, created_by=None)
        c = self._c(self.director)
        for url in ('/users/admin/', '/new/payments/?p=all', '/new/payments/%d/receipt/' % PaymentTransaction.objects.get().pk):
            self.assertLess(c.get(url).status_code, 500, url)

    @unittest.expectedFailure
    def test_QA_B05_grades_foreign_group_is_404_not_500(self):
        r = self._c(self.t1).get('/grades/teacher/groups/%d/?date=%s' % (self.g2.pk, self.today))
        self.assertIn(r.status_code, (403, 404))

    @unittest.expectedFailure
    def test_QA_N01_bad_page_param_does_not_500(self):
        c = self._c(self.admin)
        for url in ('/new/students/', '/new/groups/', '/new/payments/', '/new/payments/debtors/', '/new/messages/', '/new/settings/telegram/'):
            self.assertLess(c.get(url, {'page': 'abc'}).status_code, 500, url)

    @unittest.expectedFailure
    def test_QA_N02_huge_id_filter_does_not_500(self):
        c = self._c(self.admin)
        for url in ('/new/students/', '/new/payments/debtors/'):
            self.assertLess(c.get(url, {'group': '99999999999999999999'}).status_code, 500, url)
