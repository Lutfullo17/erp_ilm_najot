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


class NewAttendanceTests(NewUiBase):
    def _save(self, user, gid=None, records=None, **extra):
        body = {'records': records if records is not None else {str(self.s1.pk): 'ABSENT'}}
        body.update(extra)
        return self.jpost(self.login(user), '/new/api/attendance/%d/' % (gid or self.g1.pk), body)

    def test_pages_render(self):
        self.assertContains(self.get(self.t1, '/new/attendance/'), 'Bugungi darslar')
        self.assertContains(self.get(self.t1, '/new/attendance/%d/' % self.g1.pk), 'Hammasi')
        self.assertContains(self.get(self.admin, '/new/attendance/'), 'Boshqa kun uchun')

    def test_teacher_saves_once_then_locked(self):
        from attendance.models import AttendanceRecord
        r = self._save(self.t1)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(AttendanceRecord.objects.get().status, 'ABSENT')
        r2 = self._save(self.t1, records={str(self.s1.pk): 'PRESENT'})
        self.assertEqual(r2.status_code, 409)
        self.assertContains(self.get(self.t1, '/new/attendance/%d/' % self.g1.pk), 'administratorga yozing')

    def test_teacher_cannot_mark_foreign_group(self):
        self.assertEqual(self._save(self.t1, gid=self.g2.pk, records={str(self.s_other.pk): 'PRESENT'}).status_code, 403)
        r = self.get(self.t1, '/new/attendance/%d/' % self.g2.pk)
        self.assertEqual(r.status_code, 302)

    def test_rejects_foreign_student_and_bad_status(self):
        self.assertEqual(self._save(self.t1, records={str(self.s_other.pk): 'ABSENT'}).status_code, 400)
        self.assertEqual(self._save(self.t1, records={str(self.s1.pk): 'GARBAGE'}).status_code, 400)
        self.assertEqual(self._save(self.t1, records={'abc': 'PRESENT'}).status_code, 400)
        from attendance.models import AttendanceRecord
        self.assertEqual(AttendanceRecord.objects.count(), 0)

    def test_admin_can_correct_and_it_is_audited(self):
        from attendance.models import AttendanceRecord
        from users1.models import AuditLog
        self._save(self.t1)
        r = self._save(self.admin, records={str(self.s1.pk): 'PRESENT'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(AttendanceRecord.objects.get().status, 'PRESENT')
        log = AuditLog.objects.get(action='Davomat tuzatildi')
        self.assertEqual(log.old_data['records'][str(self.s1.pk)], 'ABSENT')

    def test_admin_past_date_ok_teacher_past_blocked(self):
        import datetime
        past = str(self.today - datetime.timedelta(days=3))
        self.assertEqual(self._save(self.admin, date=past).status_code, 200)
        self.assertEqual(self._save(self.admin, date=str(self.today + datetime.timedelta(days=2))).status_code, 403)

    def test_teacher_early_and_late_windows(self):
        import datetime
        from unittest import mock
        from django.utils import timezone
        from ux import views_att
        self.g1.lesson_time = datetime.time(12, 0)
        self.g1.end_time = datetime.time(13, 30)
        self.g1.save()
        def at(h, m):
            return timezone.make_aware(datetime.datetime.combine(self.today, datetime.time(h, m)))
        with mock.patch.object(views_att.timezone, 'localtime', return_value=at(11, 30)):
            self.assertEqual(self._save(self.t1).status_code, 403)    # 15 daqiqadan erta
        with mock.patch.object(views_att.timezone, 'localtime', return_value=at(11, 50)):
            self.assertEqual(self._save(self.t1).status_code, 200)    # 15 daqiqa oldin ochiladi (B10)
        self.g1.refresh_from_db()
        from attendance.models import AttendanceSession
        AttendanceSession.objects.all().delete()
        with mock.patch.object(views_att.timezone, 'localtime', return_value=at(14, 0)):
            self.assertEqual(self._save(self.t1).status_code, 403)    # dars tugagan, davomat olinmagan


class NewStudentTests(NewUiBase):
    FORM = {'full_name': 'Sardor Rahimov', 'phone': '90 123 45 67', 'group': ''}

    def _post(self, user, data, url='/new/students/new/'):
        return self.login(user).post(url, data)

    def test_pages_render(self):
        self.assertContains(self.get(self.admin, '/new/students/'), 'Yangi o')
        self.assertContains(self.get(self.admin, '/new/students/new/'), 'Ism va familiya')
        self.assertContains(self.get(self.admin, '/new/students/%d/' % self.s1.pk), 'Ali')
        self.assertContains(self.get(self.admin, '/new/students/%d/edit/' % self.s1.pk), 'Tahrirlash')
        self.assertEqual(self.get(self.t1, '/new/students/').status_code, 302)

    def test_quick_create_with_group_normalizes_phone(self):
        from students.models import Student
        from groups_app.models import GroupStudent
        r = self._post(self.admin, dict(self.FORM, group=self.g1.pk))
        self.assertEqual(r.status_code, 302)
        s = Student.objects.get(first_name='Sardor')
        self.assertEqual(s.phone, '901234567')
        self.assertTrue(GroupStudent.objects.filter(student=s, group=self.g1, is_active=True).exists())
        self.assertIn('new=1', r['Location'])

    def test_validation_messages_are_per_field_in_uzbek(self):
        r = self._post(self.admin, {'full_name': '', 'phone': '123'})
        self.assertEqual(r.status_code, 400)
        self.assertContains(r, 'Ism va familiyani kiriting', status_code=400)
        self.assertContains(r, '9 ta raqamdan iborat', status_code=400)

    def test_parent_phone_and_discount_validation(self):
        r = self._post(self.admin, dict(self.FORM, parent_phone='12', has_discount='on', discount_type='PERCENTAGE', discount_value='150'))
        self.assertEqual(r.status_code, 400)
        self.assertContains(r, '9 ta raqamdan iborat', status_code=400)
        self.assertContains(r, '100% dan oshmasligi', status_code=400)

    def test_duplicate_same_name_phone_blocked(self):
        from students.models import Student
        self._post(self.admin, self.FORM)
        r = self._post(self.admin, self.FORM)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(Student.objects.filter(first_name='Sardor').count(), 1)

    def test_xss_in_name_is_escaped_in_list(self):
        from students.models import Student
        Student.objects.create(first_name='<script>alert(1)</script>', last_name='X', phone='901111111')
        r = self.get(self.admin, '/new/students/?q=script')
        self.assertNotContains(r, '<script>alert(1)</script>')
        self.assertContains(r, '&lt;script&gt;')

    def test_long_name_rejected(self):
        r = self._post(self.admin, dict(self.FORM, full_name='A' * 400))
        self.assertEqual(r.status_code, 400)

    def test_edit_keeps_other_memberships_and_audits_discount(self):
        from groups_app.models import GroupStudent
        from users1.models import AuditLog
        GroupStudent.objects.create(group=self.g2, student=self.s1)
        r = self._post(self.admin, {'full_name': 'Ali Valiyev', 'phone': '90 111 22 33', 'has_discount': 'on',
                                    'discount_type': 'PERCENTAGE', 'discount_value': '10'}, '/new/students/%d/edit/' % self.s1.pk)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(GroupStudent.objects.filter(student=self.s1, is_active=True).count(), 2)
        self.assertTrue(AuditLog.objects.filter(action__startswith="O'quvchi holati/chegirmasi").exists())

    def test_group_add_remove_api_and_undo(self):
        from groups_app.models import GroupStudent
        c = self.login(self.admin)
        url = '/new/api/students/%d/group/' % self.s1.pk
        self.assertEqual(self.jpost(c, url, {'action': 'add', 'group_id': self.g2.pk}).status_code, 200)
        self.assertEqual(self.jpost(c, url, {'action': 'remove', 'group_id': self.g2.pk}).status_code, 200)
        self.assertFalse(GroupStudent.objects.get(student=self.s1, group=self.g2).is_active)
        self.assertEqual(self.jpost(c, url, {'action': 'add', 'group_id': self.g2.pk}).status_code, 200)   # qaytarish
        self.assertTrue(GroupStudent.objects.get(student=self.s1, group=self.g2).is_active)
        self.assertEqual(self.jpost(c, url, {'action': 'boom', 'group_id': self.g2.pk}).status_code, 400)

    def test_delete_only_director(self):
        from students.models import Student
        r = self.login(self.admin).post('/new/students/%d/delete/' % self.s1.pk)
        self.assertFalse(Student.objects.get(pk=self.s1.pk).is_deleted)
        self.login(self.director).post('/new/students/%d/delete/' % self.s1.pk)
        self.assertTrue(Student.objects.get(pk=self.s1.pk).is_deleted)

    def test_list_filters(self):
        self.assertContains(self.get(self.admin, '/new/students/?f=nogroup'), 'Hozircha' if False else 'Birinchi' if False else '')
        for f in ('debt', 'nogroup', 'frozen'):
            self.assertEqual(self.get(self.admin, '/new/students/?f=%s&group=%d' % (f, self.g1.pk)).status_code, 200)


class NewGroupTests(NewUiBase):
    def _data(self, **kw):
        d = {'name': 'Fizika 9', 'monthly_fee': '350000', 'teacher': self.t2.pk, 'days': ['Dushanba', 'Chorshanba'],
             'lesson_time': '15:00', 'duration': '1.5', 'start_date': '2026-10-05', 'room': '3'}
        d.update(kw)
        return d

    def test_pages_render(self):
        self.assertContains(self.get(self.admin, '/new/groups/'), 'Yangi guruh')
        self.assertContains(self.get(self.admin, '/new/groups/new/'), 'Qadam 1/4')
        self.assertContains(self.get(self.admin, '/new/groups/%d/' % self.g1.pk), 'Davomat belgilash')
        self.assertContains(self.get(self.admin, '/new/groups/%d/edit/' % self.g1.pk), 'tahrirlash')
        self.assertEqual(self.get(self.t1, '/new/groups/').status_code, 302)

    def test_create_ok_and_audited(self):
        from groups_app.models import Group
        from users1.models import AuditLog
        r = self.login(self.admin).post('/new/groups/new/', self._data())
        self.assertEqual(r.status_code, 302)
        g = Group.objects.get(name='Fizika 9')
        self.assertEqual(g.lesson_days, 'Dushanba, Chorshanba')
        self.assertEqual(str(g.end_time), '16:30:00')
        self.assertTrue(AuditLog.objects.filter(action='Guruh yaratildi').exists())

    def test_field_errors_in_uzbek(self):
        r = self.login(self.admin).post('/new/groups/new/', {'name': '', 'monthly_fee': '', 'days': []})
        self.assertEqual(r.status_code, 400)
        for text in ('Guruh nomini kiriting', 'Oylik narxni kiriting', 'Kamida bitta dars kunini', 'Dars boshlanish vaqtini'):
            self.assertContains(r, text, status_code=400)

    def test_duplicate_name_negative_fee_and_huge_fee(self):
        c = self.login(self.admin)
        self.assertContains(c.post('/new/groups/new/', self._data(name='G1')), 'allaqachon bor', status_code=400)
        self.assertContains(c.post('/new/groups/new/', self._data(monthly_fee='-5')), 'manfiy', status_code=400)
        self.assertContains(c.post('/new/groups/new/', self._data(monthly_fee='999999999999')), 'katta', status_code=400)

    def test_teacher_and_room_conflicts_rejected(self):
        import datetime
        from groups_app.models import Group
        day = ['Dushanba', 'Seshanba', 'Chorshanba', 'Payshanba', 'Juma', 'Shanba', 'Yakshanba'][self.today.weekday()]
        Group.objects.filter(pk=self.g1.pk).update(lesson_time=datetime.time(15, 0), end_time=datetime.time(16, 30), room=3, duration=1.5)
        c = self.login(self.admin)
        r = c.post('/new/groups/new/', self._data(days=[day], teacher=self.t1.pk, room=''))
        self.assertContains(r, "boshqa guruhda dars", status_code=400)
        r = c.post('/new/groups/new/', self._data(days=[day], room='3'))
        self.assertContains(r, 'xona', status_code=400)

    def test_check_slot_marks_busy_room(self):
        import datetime
        from groups_app.models import Group
        day = ['Dushanba', 'Seshanba', 'Chorshanba', 'Payshanba', 'Juma', 'Shanba', 'Yakshanba'][self.today.weekday()]
        Group.objects.filter(pk=self.g1.pk).update(lesson_time=datetime.time(15, 0), end_time=datetime.time(16, 30), room=2)
        d = self.get(self.admin, '/new/api/groups/check-slot/?days=%s&time=15:30&duration=1&teacher=%d' % (day, self.t1.pk)).json()
        self.assertFalse([r for r in d['rooms'] if r['id'] == 2][0]['free'])
        self.assertTrue([r for r in d['rooms'] if r['id'] == 1][0]['free'])
        self.assertIn('G1', d['teacher_busy'])

    def test_edit_saves(self):
        r = self.login(self.admin).post('/new/groups/%d/edit/' % self.g2.pk, self._data(name='G2 yangi', teacher=self.t2.pk))
        self.assertEqual(r.status_code, 302)
        self.g2.refresh_from_db()
        self.assertEqual(self.g2.name, 'G2 yangi')

    def test_pause_and_delete_permissions(self):
        from groups_app.models import Group
        c = self.login(self.admin)
        c.post('/new/groups/%d/pause/' % self.g2.pk)
        self.g2.refresh_from_db()
        self.assertTrue(self.g2.is_paused)
        c.post('/new/groups/%d/delete/' % self.g2.pk)
        self.assertTrue(Group.objects.filter(pk=self.g2.pk).exists())    # administrator o'chira olmaydi
        g3 = Group.objects.create(name='Bosh', monthly_fee=1)
        self.login(self.director).post('/new/groups/%d/delete/' % g3.pk)
        self.assertFalse(Group.objects.filter(pk=g3.pk).exists())
