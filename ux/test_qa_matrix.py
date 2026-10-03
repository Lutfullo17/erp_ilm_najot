"""QA: ruxsat matritsasi. Barcha nomli URL'larga har bir rol bilan GET/POST yuboriladi.

Tekshiruvlar:
  1) hech bir so'rov 500 qaytarmaydi (chala/yolg'on ma'lumot bilan ham);
  2) anonim foydalanuvchi ochiq bo'lmagan sahifani ocholmaydi;
  3) CSRF tokensiz POST hamma joyda rad etiladi (Telegram webhook bundan mustasno);
  4) o'qituvchi administrator sahifalarini, administrator direktor sahifalarini ocholmaydi.
"""
import json
import os
import re

from django.test import Client
from django.urls import get_resolver

from users1.test_audit_fixes import AuditBase

PUBLIC = {'/users/login/', '/bot/telegram/webhook/', '/bot/', '/grades/', '/favicon.ico', '/'}
# Ma'lum kamchiliklar (BACKEND_TEST_REPORT.md): 5-bosqichda tuzatilgach bu ro'yxat bo'shatiladi
KNOWN_500 = {('director', 'GET', '/users/administrators/new/')}           # QA-B-01: shablon yo'q
KNOWN_OPEN = {'/students/api/check-parent-phone/'}                          # QA-B-02: ruxsatsizga 403 emas, bo'sh 200
SKIP_PREFIX = ('/admin/', '/static/', '/media/')
ARG_VALUES = {'which': 'new', 'action': 'attendance', 'target_day': 'Dushanba', 'day': 'Dushanba'}

# Faqat administrator/direktor ko'ra oladigan yo'l prefikslari (o'qituvchiga 200 bo'lmasligi kerak)
ADMIN_PREFIXES = ('/students/', '/payments/', '/groups/', '/reports/', '/users/admin/', '/users/administrators/', '/users/teachers/',
                  '/users/messages/', '/users/notifications/', '/users/bot-status/', '/users/api/', '/new/payments/', '/new/students/',
                  '/new/groups/', '/new/staff/', '/new/settings/', '/new/schedule/', '/new/messages/', '/new/reports/', '/new/api/pay',
                  '/new/api/students/', '/new/api/groups/', '/new/api/payments/')
# Faqat direktor
DIRECTOR_PREFIXES = ('/users/admin/', '/users/administrators/', '/users/teachers/', '/reports/finance/', '/new/staff/',
                     '/new/settings/log/', '/users/api/broadcast-all/')
DIRECTOR_EXACT = ('/new/reports/',)
# Prefiks '/users/admin/' ostida bo'lsa ham administratorga ruxsat etilgan (kodda AdminAccess/is_admin_access)
ADMIN_ALLOWED = ('/users/admin/penalties/run-check/', '/users/admin/schedule-change-requests/', '/users/admin/penalties/alert/')
# Istisno: ruxsatni funksiyaning ichida (mixin emas) tekshiriladigan, lekin 200 qaytarishi mumkin bo'lgan yo'llar yo'q


def collect_urls():
    out = []

    def walk(patterns, prefix):
        for p in patterns:
            pat = str(p.pattern)
            if hasattr(p, 'url_patterns'):
                walk(p.url_patterns, prefix + pat)
            else:
                full = '/' + (prefix + pat).lstrip('/')
                if pat.startswith('^') or any(full.startswith(s) for s in SKIP_PREFIX):
                    continue

                def sub(m):
                    return ARG_VALUES.get(m.group(2), '1')
                path = re.sub(r'<(\w+):(\w+)>', sub, full)
                out.append((path, p.name))
    walk(get_resolver().url_patterns, '')
    return sorted(set(out))


class PermissionMatrixTests(AuditBase):
    maxDiff = None

    def clients(self):
        return {'anon': Client(), 'teacher': self.login(self.t1), 'administrator': self.login(self.admin), 'director': self.login(self.director)}

    def setUp(self):
        super().setUp()
        for c in (self.t1, self.admin, self.director):
            pass

    def _call(self, client, method, path):
        client.raise_request_exception = False
        try:
            if method == 'GET':
                return client.get(path)
            return client.post(path, json.dumps({}), content_type='application/json')
        except Exception as exc:  # pragma: no cover
            self.fail(f'{method} {path}: {exc!r}')

    def test_no_500_for_any_role_and_method(self):
        urls = collect_urls()
        self.assertGreater(len(urls), 100)
        bad, matrix = [], []
        for role, client in self.clients().items():
            for path, name in urls:
                if path in ('/users/logout/',) :
                    continue
                for method in ('GET', 'POST'):
                    r = self._call(client, method, path)
                    matrix.append((role, method, path, r.status_code))
                    if path == '/bot/telegram/webhook/' and r.status_code == 503:
                        continue   # secret sozlanmagan: ataylab 503 (K-2 tuzatishi)
                    if r.status_code >= 500 and (role, method, path) not in KNOWN_500:
                        bad.append((role, method, path, r.status_code))
        if os.environ.get('QA_MATRIX_OUT'):
            with open(os.environ['QA_MATRIX_OUT'], 'w', encoding='utf-8') as f:
                for row in matrix:
                    f.write('\t'.join(map(str, row)) + '\n')
        self.assertEqual(bad, [], f'{len(bad)} ta 500 xato: {bad[:10]}')

    def test_anonymous_never_gets_protected_page(self):
        leaks = []
        client = Client()
        for path, name in collect_urls():
            if path in PUBLIC or path.startswith('/new/switch/') or path == '/users/logout/':
                continue
            r = self._call(client, 'GET', path)
            if r.status_code == 200 and path not in KNOWN_OPEN:
                leaks.append(path)
        self.assertEqual(leaks, [], f'Anonim 200 olgan sahifalar: {leaks}')

    def test_csrf_enforced_on_every_post(self):
        client = Client(enforce_csrf_checks=True)
        client.login(username='adm', password='pw-12345')
        missing = []
        for path, name in collect_urls():
            if path in ('/bot/telegram/webhook/', '/users/login/', '/users/logout/'):
                continue
            r = self._call(client, 'POST', path)
            if r.status_code not in (403,):
                if r.status_code == 405:      # faqat GET qabul qiladigan view — POST uchun CSRF ahamiyatsiz
                    continue
                missing.append((path, r.status_code))
        self.assertEqual(missing, [], f'CSRFsiz POST rad etilmagan: {missing[:15]}')

    def test_teacher_cannot_open_admin_pages(self):
        client = self.login(self.t1)
        leaks = []
        for path, name in collect_urls():
            if any(path.startswith(p) for p in ADMIN_PREFIXES) and path not in KNOWN_OPEN:
                for method in ('GET', 'POST'):
                    r = self._call(client, method, path)
                    if r.status_code == 200:
                        leaks.append((method, path))
        self.assertEqual(leaks, [], f"O'qituvchi 200 olgan administrator sahifalari: {leaks}")

    def test_administrator_cannot_open_director_pages(self):
        client = self.login(self.admin)
        leaks = []
        for path, name in collect_urls():
            if (any(path.startswith(p) for p in DIRECTOR_PREFIXES) or path in DIRECTOR_EXACT) and not path.startswith(ADMIN_ALLOWED):
                for method in ('GET', 'POST'):
                    r = self._call(client, method, path)
                    if r.status_code in (200, 201):
                        leaks.append((method, path, r.status_code))
        self.assertEqual(leaks, [], f'Administrator 200 olgan direktor sahifalari: {leaks}')
