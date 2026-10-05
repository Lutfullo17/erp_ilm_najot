from attendance.models import AttendanceRecord, AttendanceSession, AttendanceStatus
from groups_app.models import GroupStudent
from students.models import Student
from users1.test_audit_fixes import AuditBase


class TodayAttendanceReportTests(AuditBase):
	def test_report_counts_group_roster_and_attendance_statuses(self):
		session = AttendanceSession.objects.create(group=self.g1, teacher=self.t1, date=self.today)
		memberships = [GroupStudent.objects.get(group=self.g1, student=self.s1)]
		for index in range(14):
			student = Student.objects.create(first_name=f'Oquvchi{index}', last_name='Test')
			memberships.append(GroupStudent.objects.create(group=self.g1, student=student))
		for membership in memberships[:10]:
			AttendanceRecord.objects.create(session=session, student=membership.student, status=AttendanceStatus.PRESENT)
		for membership in memberships[10:]:
			AttendanceRecord.objects.create(session=session, student=membership.student, status=AttendanceStatus.ABSENT)

		response = self.login(self.admin).get('/reports/attendance/today/')

		self.assertEqual(response.status_code, 200)
		stats = response.context['attendance_stats'][0]
		self.assertEqual((stats['total'], stats['present'], stats['absent'], stats['unmarked']), (15, 10, 5, 0))
		self.assertContains(response, '15')
		self.assertContains(response, '10')
		self.assertContains(response, '5')

	def test_group_attendance_detail_lists_each_students_status(self):
		session = AttendanceSession.objects.create(group=self.g1, teacher=self.t1, date=self.today)
		AttendanceRecord.objects.create(session=session, student=self.s1, status=AttendanceStatus.PRESENT)

		response = self.login(self.admin).get(f'/reports/attendance/today/{self.g1.pk}/')

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Valiyev Ali')
		self.assertContains(response, 'Keldi')
		self.assertContains(response, 'Belgilanmagan')
		self.assertEqual(response.context['total'], 1)
