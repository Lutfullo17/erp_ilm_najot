import datetime
from unittest import mock
from django.test import TestCase
from users1.models import User, ScheduleChangeRequest
from groups_app.models import Group
from bot.models import TelegramUser
from students.models import Student
from groups_app.models import GroupStudent


class NotifyProof(TestCase):
    def test_schedule_notification_never_sends(self):
        t = User.objects.create(username='t', role='TEACHER')
        g = Group.objects.create(name='G', teacher=t, monthly_fee=1)
        s = Student.objects.create(first_name='a', last_name='b')
        GroupStudent.objects.create(group=g, student=s)
        TelegramUser.objects.create(telegram_id=5, student=s, is_verified=True)
        req = ScheduleChangeRequest.objects.create(
            teacher=t, group=g, old_day='Dushanba', old_start_time=datetime.time(9), old_end_time=datetime.time(10),
            new_day='Juma', new_start_time=datetime.time(9), new_end_time=datetime.time(10), reason='x')
        from users1 import services
        with mock.patch('bot.services.send_telegram_message') as sm, self.assertLogs('users1.services', 'ERROR') as lg:
            services.send_schedule_change_notifications(req)
        print('\nsend calls:', sm.call_count, '| log:', lg.output[0][:160])
        self.assertEqual(sm.call_count, 0)
