import datetime

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from unittest.mock import patch

from groups_app.models import Group, GroupStudent
from attendance.models import AttendanceSession
from students.models import Student
from users1.models import User, MissedAttendanceAlert, TeacherPenalty, ScheduleChangeRequest
from users1.penalty_service import check_and_create_missed_alerts
from users1.views import ScheduleChangeRequestForm


def _today_name():
    day_names = ['Dushanba', 'Seshanba', 'Chorshanba', 'Payshanba', 'Juma', 'Shanba', 'Yakshanba']
    return day_names[timezone.localdate().weekday()]


def _time_minus(minutes):
    now = timezone.localtime()
    return (now - datetime.timedelta(minutes=minutes)).time()


class ScheduleChangeRequestFormTestCase(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(
            username='teacher_schedule_test',
            password='password',
            role=User.Role.TEACHER,
        )
        self.group = Group.objects.create(
            name='Schedule Override Group',
            teacher=self.teacher,
            lesson_days='Dushanba,Chorshanba',
            lesson_time=datetime.time(10, 0),
            end_time=datetime.time(11, 0),
            is_active=True,
            start_date=timezone.localdate() - datetime.timedelta(days=7),
        )

    def test_teacher_schedule_view_applies_a_one_week_override_and_reverts_next_week(self):
        self.client.force_login(self.teacher)
        self.group.lesson_days = 'Dushanba,Chorshanba'
        self.group.lesson_time = datetime.time(10, 0)
        self.group.end_time = datetime.time(11, 0)
        self.group.save()

        request = ScheduleChangeRequest.objects.create(
            teacher=self.teacher,
            group=self.group,
            old_day='Dushanba',
            old_start_time=datetime.time(10, 0),
            old_end_time=datetime.time(11, 0),
            new_day='Seshanba',
            new_start_time=datetime.time(12, 0),
            new_end_time=datetime.time(13, 0),
            reason='Test',
            status=ScheduleChangeRequest.Status.APPROVED,
            effective_week_start=timezone.localdate() - timezone.timedelta(days=timezone.localdate().weekday()),
        )

        response_this_week = self.client.get(reverse('users1:teacher_schedule'))
        self.assertEqual(response_this_week.status_code, 200)
        this_week_days = response_this_week.context['week_days']
        seshanba_lessons = [lesson for day in this_week_days if day['day_name'] == 'Seshanba' for lesson in day['lessons'] if lesson['group'].pk == self.group.pk]
        dushanba_lessons = [lesson for day in this_week_days if day['day_name'] == 'Dushanba' for lesson in day['lessons'] if lesson['group'].pk == self.group.pk]
        self.assertTrue(seshanba_lessons)
        self.assertFalse(dushanba_lessons)

        response_next_week = self.client.get(reverse('users1:teacher_schedule'), {'week_offset': 1})
        self.assertEqual(response_next_week.status_code, 200)
        next_week_days = response_next_week.context['week_days']
        next_week_seshanba_lessons = [lesson for day in next_week_days if day['day_name'] == 'Seshanba' for lesson in day['lessons'] if lesson['group'].pk == self.group.pk]
        next_week_dushanba_lessons = [lesson for day in next_week_days if day['day_name'] == 'Dushanba' for lesson in day['lessons'] if lesson['group'].pk == self.group.pk]
        self.assertFalse(next_week_seshanba_lessons)
        self.assertTrue(next_week_dushanba_lessons)

    def test_schedule_change_form_accepts_24_hour_time_format(self):
        form = ScheduleChangeRequestForm(
            data={
                'new_day': 'Dushanba',
                'new_start_time': '14:30',
                'reason': 'Test sabab',
            },
            group=None,
            teacher=None,
            old_day='Dushanba',
            old_start_time=datetime.time(10, 0),
            old_end_time=datetime.time(11, 0),
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['new_start_time'], datetime.time(14, 30))

    def test_schedule_change_form_rejects_ampm_format(self):
        form = ScheduleChangeRequestForm(
            data={
                'new_day': 'Dushanba',
                'new_start_time': '2:30 PM',
                'reason': 'Test sabab',
            },
            group=None,
            teacher=None,
            old_day='Dushanba',
            old_start_time=datetime.time(10, 0),
            old_end_time=datetime.time(11, 0),
        )

        self.assertFalse(form.is_valid())
        self.assertIn('new_start_time', form.errors)

    def test_schedule_change_form_computes_end_time_from_duration(self):
        self.group.duration = 1.5
        self.group.save(update_fields=['duration'])

        form = ScheduleChangeRequestForm(
            data={
                'new_day': 'Dushanba',
                'new_start_time': '14:30',
                'reason': 'Test sabab',
            },
            group=self.group,
            teacher=self.teacher,
            old_day='Dushanba',
            old_start_time=datetime.time(10, 0),
            old_end_time=datetime.time(11, 0),
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['new_end_time'], datetime.time(16, 0))

    def test_schedule_change_form_rejects_moving_to_earlier_day(self):
        form = ScheduleChangeRequestForm(
            data={
                'new_day': 'Dushanba',
                'new_start_time': '14:30',
                'reason': 'Test sabab',
            },
            group=self.group,
            teacher=self.teacher,
            old_day='Seshanba',
            old_start_time=datetime.time(10, 0),
            old_end_time=datetime.time(11, 0),
        )

        self.assertFalse(form.is_valid())
        self.assertIn('Darsni avvalgi kungacha', str(form.errors))


class MissedAttendanceWorkflowTestCase(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(
            username='teacher1',
            password='password',
            role=User.Role.TEACHER,
        )
        self.director = User.objects.create_user(
            username='director1',
            password='password',
            role=User.Role.DIRECTOR,
        )
        self.group = Group.objects.create(
            name='Test Group',
            teacher=self.teacher,
            lesson_days=_today_name(),
            lesson_time=_time_minus(120),
            end_time=_time_minus(30),
            is_active=True,
            start_date=timezone.localdate() - datetime.timedelta(days=7),
        )
        self.student = Student.objects.create(
            first_name='Test',
            last_name='Student',
            is_active=True,
        )
        GroupStudent.objects.create(group=self.group, student=self.student, is_active=True)

    def test_check_and_create_missed_alerts_creates_alert_when_session_missing(self):
        self.assertFalse(AttendanceSession.objects.filter(group=self.group, date=timezone.localdate()).exists())

        created_count = check_and_create_missed_alerts()

        self.assertEqual(created_count, 1)
        alert = MissedAttendanceAlert.objects.filter(group=self.group, lesson_date=timezone.localdate()).first()
        self.assertIsNotNone(alert)
        self.assertEqual(alert.status, MissedAttendanceAlert.Status.PENDING)

    def test_check_and_create_missed_alerts_does_not_create_if_session_exists(self):
        AttendanceSession.objects.create(group=self.group, teacher=self.teacher, date=timezone.localdate())

        created_count = check_and_create_missed_alerts()

        self.assertEqual(created_count, 0)
        self.assertFalse(MissedAttendanceAlert.objects.filter(group=self.group, lesson_date=timezone.localdate()).exists())

    def test_resolve_missed_alert_as_came_creates_attendance_penalty(self):
        alert = MissedAttendanceAlert.objects.create(
            teacher=self.teacher,
            group=self.group,
            lesson_date=timezone.localdate(),
            status=MissedAttendanceAlert.Status.PENDING,
        )
        self.client.force_login(self.director)

        response = self.client.post(
            reverse('users1:resolve_missed_alert', kwargs={'alert_pk': alert.pk}),
            data={'decision': 'came'},
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        alert.refresh_from_db()
        self.assertEqual(alert.status, MissedAttendanceAlert.Status.CAME)
        self.assertTrue(alert.penalty_applied)
        penalty = TeacherPenalty.objects.filter(teacher=self.teacher, group=self.group, date=timezone.localdate()).first()
        self.assertIsNotNone(penalty)
        self.assertEqual(penalty.points, -5)
        self.assertEqual(penalty.penalty_type, TeacherPenalty.PenaltyType.ATTENDANCE_MISSED)

    def test_resolve_missed_alert_as_not_came_creates_stronger_penalty(self):
        alert = MissedAttendanceAlert.objects.create(
            teacher=self.teacher,
            group=self.group,
            lesson_date=timezone.localdate(),
            status=MissedAttendanceAlert.Status.PENDING,
        )
        self.client.force_login(self.director)

        response = self.client.post(
            reverse('users1:resolve_missed_alert', kwargs={'alert_pk': alert.pk}),
            data={'decision': 'not_came'},
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        alert.refresh_from_db()
        self.assertEqual(alert.status, MissedAttendanceAlert.Status.NOT_CAME)
        self.assertTrue(alert.penalty_applied)
        penalty = TeacherPenalty.objects.filter(teacher=self.teacher, group=self.group, date=timezone.localdate()).first()
        self.assertIsNotNone(penalty)
        self.assertEqual(penalty.points, -10)
        self.assertEqual(penalty.penalty_type, TeacherPenalty.PenaltyType.CLASS_SKIPPED)

    def test_teacher_schedule_view_builds_weekly_timetable(self):
        self.client.force_login(self.teacher)

        response = self.client.get(reverse('users1:teacher_schedule'))

        self.assertEqual(response.status_code, 200)
        self.assertIn('week_days', response.context)
        self.assertEqual(len(response.context['week_days']), 7)
        self.assertTrue(any(day['lessons'] for day in response.context['week_days']))

    def test_teacher_schedule_view_supports_next_week_navigation(self):
        self.client.force_login(self.teacher)

        response = self.client.get(reverse('users1:teacher_schedule'), {'week_offset': 1})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['week_offset'], 1)
        expected_start = timezone.localdate() - timezone.timedelta(days=timezone.localdate().weekday()) + timezone.timedelta(days=7)
        self.assertEqual(response.context['week_days'][0]['date'], expected_start)
