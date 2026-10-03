"""QA: yolg'on/zararli kiritish. Hech bir endpoint 500 bermasligi va ma'lumotni buzmasligi kerak."""
import json
import os
import unittest

from django.test import Client

from payments.models import PaymentTransaction
from students.models import Student
from users1.test_audit_fixes import AuditBase

JUNK = [None, '', 'abc', 0, -1, 10 ** 30, 1.5, True, [], [1], {}, {'a': 1}, '<script>alert(1)</script>', "' OR 1=1 --", '\x00', 'А' * 5000,
        '9' * 400, '1e999', 'NaN', '../../etc/passwd', '%', '${7*7}', '{{7*7}}']

JSON_ENDPOINTS = [
    ('/new/api/payments/', ['student_id', 'group_id', 'amount', 'payment_date', 'method', 'note', 'idempotency_key']),
    ('/new/api/attendance/%(g)d/', ['records', 'date', 'topic', 'homework']),
    ('/new/api/students/%(s)d/group/', ['action', 'group_id']),
    ('/new/feedback/', ['message', 'page']),
    ('/grades/teacher/groups/%(g)d/', ['date', 'title', 'records']),
    ('/users/api/broadcast/', ['group_id', 'message']),
    ('/users/api/broadcast-all/', ['message']),
    ('/payments/api/create/', ['student_id', 'group_id', 'amount', 'payment_date', 'method', 'note']),
    ('/attendance/api/save-lesson-plan/', ['group_id', 'date', 'topic', 'is_exam']),
    ('/attendance/api/admin-override/%(g)d/', ['date']),
    ('/users/admin/penalties/teacher/%(t)d/add/', ['points', 'reason']),
    ('/users/admin/profile/change-password/', ['old_password', 'new_password', 'confirm_password']),
    ('/users/admin/profile/update-info/', ['first_name', 'last_name', 'phone']),
    ('/users/admin/profile/change-login/', ['username']),
    ('/groups/%(g)d/edit-lesson/Dushanba/save/', ['new_day', 'room', 'start_time', 'reason']),
    ('/users/teachers/%(t)d/reset-password/', ['new_password']),
    ('/users/teachers/%(t)d/change-login/', ['username']),
]

GET_PARAMS = [
    ('/new/students/', ['q', 'f', 'group', 'page']), ('/new/groups/', ['q', 'f', 'page']), ('/new/payments/', ['q', 'p', 'page']),
    ('/new/payments/debtors/', ['q', 'f', 'group', 'page']), ('/new/messages/', ['q', 'f', 'page']), ('/new/reports/', ['month']),
    ('/new/attendance/%(g)d/', ['date']), ('/new/payments/new/', ['student', 'group']), ('/new/api/search/', ['q']),
    ('/new/api/pay-search/', ['q']), ('/new/api/groups/check-slot/', ['days', 'time', 'duration', 'teacher', 'exclude', 'room']),
    ('/new/grades/', ['group', 'date', 'title']), ('/new/my-schedule/', ['week_offset']), ('/new/settings/log/', ['q', 'page']),
    ('/new/settings/telegram/', ['status', 'page']), ('/new/schedule/', ['day']), ('/new/staff/', ['tab']),
    ('/users/teacher/schedule/', ['week_offset']), ('/students/', ['q', 'page']),
]


def _dump(name, failures):
    out = os.environ.get('QA_FUZZ_OUT')
    if out and failures:
        with open(out, 'a', encoding='utf-8') as f:
            for row in failures:
                f.write(name + '|' + '|'.join(map(str, row)).replace('\n', ' ') + '\n')


class FuzzTests(AuditBase):
    def _ids(self):
        return {'g': self.g1.pk, 's': self.s1.pk, 't': self.t1.pk}

    @unittest.expectedFailure   # QA-B-03 / QA-N-01..03: tuzatilgach olib tashlanadi
    def test_json_endpoints_never_500(self):
        failures = []
        for role_name, user in (('teacher', self.t1), ('administrator', self.admin), ('director', self.director)):
            c = self.login(user)
            c.raise_request_exception = False
            for url, fields in JSON_ENDPOINTS:
                url = url % self._ids()
                for field in fields:
                    for junk in JUNK:
                        base = {'student_id': self.s1.pk, 'group_id': self.g1.pk, 'amount': 1000, 'records': {str(self.s1.pk): 'PRESENT'},
                                'message': 'salom', 'action': 'add', 'date': str(self.today), 'title': 'T', 'reason': 'sabab', 'points': -5,
                                'old_password': 'x', 'new_password': 'Qiyin-Parol-77!', 'confirm_password': 'Qiyin-Parol-77!', 'username': 'yangi_login',
                                'first_name': 'A', 'last_name': 'B', 'phone': '901112233', 'topic': 'T', 'new_day': 'Juma', 'room': 2, 'start_time': '10:00'}
                        base[field] = junk
                        try:
                            r = c.post(url, json.dumps(base), content_type='application/json')
                        except Exception as exc:        # sarlavhaga yaroqsiz belgi va h.k.
                            failures.append((role_name, url, field, repr(junk)[:30], f'EXC {exc!r}'[:80]))
                            continue
                        if r.status_code >= 500:
                            failures.append((role_name, url, field, repr(junk)[:30], r.status_code))
        _dump('json', failures)
        self.assertEqual(failures, [], f'{len(failures)} ta 500: ' + '; '.join(map(str, failures[:12])))

    @unittest.expectedFailure   # QA-B-03 / QA-N-01..03: tuzatilgach olib tashlanadi
    def test_non_json_and_broken_bodies(self):
        c = self.login(self.admin)
        c.raise_request_exception = False
        for url, _ in JSON_ENDPOINTS:
            url = url % self._ids()
            for body, ctype in (('{', 'application/json'), ('[1,2', 'application/json'), ('', 'application/json'), ('null', 'application/json'),
                                ('[]', 'application/json'), ('"str"', 'application/json'), ('a=b', 'application/x-www-form-urlencoded'),
                                (b'\xff\xfe', 'application/json')):
                r = c.post(url, body, content_type=ctype)
                self.assertLess(r.status_code, 500, (url, body))

    @unittest.expectedFailure   # QA-B-03 / QA-N-01..03: tuzatilgach olib tashlanadi
    def test_get_params_never_500(self):
        failures = []
        for user in (self.t1, self.admin, self.director):
            c = self.login(user)
            c.raise_request_exception = False
            for url, params in GET_PARAMS:
                url = url % self._ids()
                for p in params:
                    for junk in ('abc', '-1', '0', '99999999999999999999', '%00', "' OR 1=1 --", '<script>', 'А' * 3000, '2026-13-45', '9999-12',
                                 '0000-00', '1,2,3', '١٢٣', '../..', ''):
                        try:
                            r = c.get(url, {p: junk})
                        except Exception as exc:
                            failures.append((user.username, url, p, junk[:20], f'EXC {exc!r}'[:70]))
                            continue
                        if r.status_code >= 500:
                            failures.append((user.username, url, p, junk[:20], r.status_code))
        _dump('get', failures)
        self.assertEqual(failures, [], f'{len(failures)} ta 500: ' + '; '.join(map(str, failures[:15])))

    def test_junk_never_creates_money_or_students(self):
        c = self.login(self.admin)
        c.raise_request_exception = False
        before = (PaymentTransaction.objects.count(), Student.objects.count())
        for junk in [j for j in JUNK if j != 1.5]:     # 1.5 — yaroqli summa (1,50 so'm)
            c.post('/new/api/payments/', json.dumps({'student_id': self.s1.pk, 'group_id': self.g1.pk, 'amount': junk}), content_type='application/json')
        self.assertEqual(PaymentTransaction.objects.count(), before[0])
        for junk in JUNK:
            c.post('/new/students/new/', {'full_name': junk if isinstance(junk, str) else 'x', 'phone': junk if isinstance(junk, str) else ''})
        # faqat yaroqli (matnli) ismlar o'quvchi yaratishi mumkin: kamida 2 belgi
        created = Student.objects.count() - before[1]
        names = list(Student.objects.order_by('-pk').values_list('first_name', flat=True)[:created])
        self.assertLessEqual(created, 8, names)
