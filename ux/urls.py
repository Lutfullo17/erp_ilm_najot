from django.urls import path

from . import (views_att, views_groups, views_home, views_misc, views_msg, views_pay, views_reports, views_sched,
               views_settings, views_staff, views_students)

app_name = 'new'

urlpatterns = [
    path('', views_home.HomeView.as_view(), name='home'),
    path('switch/<str:which>/', views_home.switch_ui, name='switch'),
    path('api/search/', views_misc.api_search, name='api_search'),
    path('feedback/', views_misc.feedback, name='feedback'),

    # --- To'lov
    path('payments/new/', views_pay.PayView.as_view(), name='pay'),
    path('payments/debtors/', views_pay.DebtorsView.as_view(), name='debtors'),
    path('payments/', views_pay.PaymentsView.as_view(), name='payments'),
    path('payments/<int:pk>/receipt/', views_pay.receipt, name='receipt'),
    path('payments/<int:pk>/delete/', views_pay.payment_delete, name='payment_delete'),
    path('api/pay-search/', views_pay.api_pay_search, name='api_pay_search'),
    path('api/pay-info/<int:pk>/', views_pay.api_pay_info, name='api_pay_info'),
    path('api/payments/', views_pay.api_pay_create, name='api_pay_create'),
    path('api/payments/<int:pk>/undo/', views_pay.api_pay_undo, name='api_pay_undo'),

    # --- Davomat
    path('attendance/', views_att.AttendanceListView.as_view(), name='attendance'),
    path('attendance/<int:gid>/', views_att.AttendanceMarkView.as_view(), name='attendance_mark'),
    path('api/attendance/<int:gid>/', views_att.api_attendance, name='api_attendance'),

    # --- O'quvchilar
    path('students/', views_students.StudentsView.as_view(), name='students'),
    path('students/new/', views_students.StudentNewView.as_view(), name='student_new'),
    path('students/<int:pk>/', views_students.StudentDetailView.as_view(), name='student'),
    path('students/<int:pk>/edit/', views_students.StudentEditView.as_view(), name='student_edit'),
    path('students/<int:pk>/delete/', views_students.student_delete, name='student_delete'),
    path('api/students/<int:pk>/group/', views_students.api_student_group, name='api_student_group'),

    # --- Guruhlar
    path('groups/', views_groups.GroupsView.as_view(), name='groups'),
    path('groups/new/', views_groups.GroupNewView.as_view(), name='group_new'),
    path('groups/<int:pk>/', views_groups.GroupDetailView.as_view(), name='group'),
    path('groups/<int:pk>/edit/', views_groups.GroupEditView.as_view(), name='group_edit'),
    path('groups/<int:pk>/pause/', views_groups.group_pause, name='group_pause'),
    path('groups/<int:pk>/delete/', views_groups.group_delete, name='group_delete'),
    path('api/groups/check-slot/', views_groups.api_check_slot, name='api_check_slot'),

    # --- Dars jadvali
    path('schedule/', views_sched.ScheduleView.as_view(), name='schedule'),
    path('schedule/review/<int:pk>/', views_sched.schedule_review, name='schedule_review'),
    path('my-schedule/', views_sched.MyScheduleView.as_view(), name='my_schedule'),
    path('my-schedule/request/<int:gid>/', views_sched.RequestNewView.as_view(), name='request_new'),

    # --- Xabarlar
    path('messages/', views_msg.MessagesView.as_view(), name='messages'),

    # --- Xodimlar
    path('staff/', views_staff.StaffView.as_view(), name='staff'),
    path('staff/teachers/new/', views_staff.TeacherNewView.as_view(), name='teacher_new'),
    path('staff/teachers/<int:pk>/', views_staff.TeacherDetailNewView.as_view(), name='staff_teacher'),
    path('staff/teachers/<int:pk>/edit/', views_staff.TeacherEditView.as_view(), name='teacher_edit'),
    path('staff/teachers/<int:pk>/delete/', views_staff.teacher_delete, name='teacher_delete'),
    path('staff/admins/new/', views_staff.AdminNewView.as_view(), name='admin_new'),

    # --- Hisobotlar va sozlamalar
    path('reports/', views_reports.FinanceReportNewView.as_view(), name='report'),
    path('reports/attendance/', views_reports.TodayAttendanceNewView.as_view(), name='report_attendance'),
    path('settings/', views_settings.SettingsView.as_view(), name='settings'),
    path('settings/telegram/', views_settings.TelegramStatusView.as_view(), name='telegram'),
    path('settings/log/', views_settings.AuditView.as_view(), name='audit'),

    # --- O'qituvchi
    path('profile/', views_settings.ProfileView.as_view(), name='profile'),
    path('grades/', views_sched.GradesView.as_view(), name='grades'),
    path('my-groups/', views_sched.MyGroupsView.as_view(), name='my_groups'),
    path('my-groups/<int:pk>/', views_sched.MyGroupView.as_view(), name='my_group'),
    path('my-students/', views_sched.MyStudentsView.as_view(), name='my_students'),
    path('my-students/<int:pk>/', views_sched.MyStudentView.as_view(), name='my_student'),
]
