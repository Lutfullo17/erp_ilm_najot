import datetime
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from groups_app.models import Group
from users1.models import MissedAttendanceAlert, User
from users1.notifications import DAY_NAMES

STATIC = {'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}}


@override_settings(STORAGES=STATIC)
class NotificationsPageTests(TestCase):
    def setUp(self):
        self.director = User.objects.create_user(username='dir', password='x', role=User.Role.DIRECTOR)
        self.admin = User.objects.create_user(username='adm', password='x', role=User.Role.ADMINISTRATOR)
        self.teacher = User.objects.create_user(username='t', password='x', role=User.Role.TEACHER, first_name='Ali')
        now = timezone.localtime().replace(hour=15, minute=0)
        self.now = now
        self.group = Group.objects.create(
            name='Arab tili', monthly_fee=100, teacher=self.teacher,
            lesson_days=DAY_NAMES[now.weekday()], lesson_time=datetime.time(8, 0), duration=1,
        )
        Group.objects.filter(pk=self.group.pk).update(end_time=datetime.time(9, 0))
        for i in range(3):
            g = Group.objects.create(name=f'G{i}', monthly_fee=100)
            MissedAttendanceAlert.objects.create(
                teacher=self.teacher, group=g, lesson_date=now.date() - datetime.timedelta(days=i + 1),
                status=MissedAttendanceAlert.Status.NOT_CAME, penalty_applied=True,
            )
        MissedAttendanceAlert.objects.create(teacher=self.teacher, group=self.group, lesson_date=now.date())

    def get(self, user, name):
        self.client.force_login(user)
        with patch('django.utils.timezone.localtime', return_value=self.now):
            return self.client.get(reverse(name))

    def test_director_dashboard_has_no_alerts(self):
        html = self.get(self.director, 'users1:admin_dashboard').content.decode()
        self.assertNotIn('Davomat olinmagan!', html)
        self.assertNotIn("3 ta darsda davomat yo'q", html)

    def test_administrator_dashboard_has_no_alerts(self):
        html = self.get(self.admin, 'users1:administrator_dashboard').content.decode()
        self.assertNotIn('Davomat olinmagan!', html)
        self.assertNotIn("O'qituvchi darsga keldimi?", html)

    def test_notifications_page_lists_everything(self):
        resp = self.get(self.director, 'users1:notifications')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual([g.name for g in resp.context['missing_attendance']], ['Arab tili'])
        self.assertEqual(list(resp.context['teachers_with_3_consecutive']), [self.teacher])
        self.assertEqual(resp.context['pending_alerts'].count(), 1)
        # menyu belgisi: 1 davomat olinmagan + 1 kutilayotgan ogohlantirish
        self.assertEqual(resp.context['notification_count'], 2)
        self.assertContains(resp, reverse('users1:notifications'))

    def test_teacher_cannot_open_notifications(self):
        resp = self.get(self.teacher, 'users1:notifications')
        self.assertNotEqual(resp.status_code, 200)
