from django.urls import path
from django.contrib.auth.views import LogoutView

from . import views

app_name = 'users1'

urlpatterns = [
    path('', views.index, name='index'),
    path('login/', views.RoleLoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),

    # ── Director ───────────────────────────────────────────────────────────
    path('admin/', views.AdminDashboardView.as_view(), name='admin_dashboard'),
    path('admin/profile/', views.DirectorProfileView.as_view(), name='director_profile'),
    path('admin/profile/change-login/', views.director_change_login, name='director_change_login'),
    path('admin/profile/update-info/', views.director_update_info, name='director_update_info'),
    path('admin/profile/change-password/', views.director_change_password, name='director_change_password'),
    path('admin/profile/change-photo/', views.director_change_photo, name='director_change_photo'),
    path('admin/audit-log/', views.AuditLogView.as_view(), name='audit_log'),

    # ── Penalty System ─────────────────────────────────────────────────────
    path('admin/penalties/', views.PenaltyListView.as_view(), name='penalty_list'),
    path('admin/penalties/teacher/<int:teacher_pk>/add/', views.director_add_penalty, name='add_penalty'),
    path('admin/penalties/alert/<int:alert_pk>/resolve/', views.resolve_missed_alert, name='resolve_missed_alert'),
    path('admin/penalties/<int:penalty_pk>/edit/', views.edit_penalty, name='edit_penalty'),
    path('admin/penalties/<int:penalty_pk>/delete/', views.delete_penalty, name='delete_penalty'),
    path('admin/penalties/run-check/', views.run_attendance_check, name='run_attendance_check'),

    # ── Administrator Management (Director only) ────────────────────────────
    path('administrators/', views.AdministratorListView.as_view(), name='administrator_list'),
    path('administrators/new/', views.AdministratorCreateView.as_view(), name='administrator_create'),
    path('administrators/<int:pk>/change-login/', views.director_change_admin_login, name='admin_change_login'),
    path('administrators/<int:pk>/reset-password/', views.director_reset_admin_password, name='admin_reset_password'),
    path('administrators/<int:pk>/toggle-block/', views.director_toggle_admin_block, name='admin_toggle_block'),

    # ── Teacher Management (Director only) ─────────────────────────────────
    path('teachers/', views.TeacherListView.as_view(), name='teacher_list'),
    path('teachers/new/', views.TeacherCreateView.as_view(), name='teacher_create'),
    path('teachers/<int:pk>/', views.TeacherDetailView.as_view(), name='teacher_detail'),
    path('teachers/<int:pk>/edit/', views.TeacherUpdateView.as_view(), name='teacher_edit'),
    path('teachers/<int:pk>/delete/', views.delete_teacher, name='teacher_delete'),
    path('teachers/<int:pk>/change-login/', views.director_change_teacher_login, name='teacher_change_login'),
    path('teachers/<int:pk>/reset-password/', views.director_reset_teacher_password, name='teacher_reset_password'),

    # ── Administrator Portal ────────────────────────────────────────────────
    path('administrator/', views.AdministratorDashboardView.as_view(), name='administrator_dashboard'),
    path('administrator/profile/', views.AdministratorProfileView.as_view(), name='administrator_profile'),

    # ── Bot holati ──────────────────────────────────────────────────
    path('bot-status/', views.BotStatusView.as_view(), name='bot_status'),

    # ── Teacher Portal ──────────────────────────────────────────────────────
    path('teacher/', views.TeacherDashboardView.as_view(), name='teacher_dashboard'),
    path('teacher/current-lesson/<str:action>/', views.teacher_current_lesson_action, name='teacher_current_lesson_action'),
    path('teacher/groups/', views.TeacherGroupsView.as_view(), name='teacher_groups'),
    path('teacher/groups/<int:pk>/', views.TeacherGroupDetailView.as_view(), name='teacher_group_detail'),
    path('teacher/schedule/', views.TeacherScheduleView.as_view(), name='teacher_schedule'),
    path('teacher/students/', views.TeacherStudentsView.as_view(), name='teacher_students'),
    path('teacher/students/<int:pk>/', views.TeacherStudentDetailView.as_view(), name='teacher_student_detail'),
    path('teacher/profile/', views.TeacherProfileView.as_view(), name='teacher_profile'),
    path('teacher/groups/<int:group_pk>/schedule-change-request/', views.ScheduleChangeRequestCreateView.as_view(), name='schedule_change_request_create'),
    path('teacher/schedule-change-requests/', views.TeacherScheduleRequestHistoryView.as_view(), name='teacher_schedule_request_history'),

    path('schedule-change-requests/<int:request_pk>/', views.ScheduleChangeRequestDetailView.as_view(), name='schedule_change_request_detail'),
    path('schedule-change-requests/<int:request_pk>/review/', views.review_schedule_change_request, name='schedule_change_request_review'),

    # ── API ─────────────────────────────────────────────────────────────────
    path('api/reply/<int:appeal_id>/', views.reply_appeal, name='reply_appeal'),
    path('api/resolve/<int:appeal_id>/', views.resolve_appeal, name='resolve_appeal'),
    path('api/broadcast/', views.broadcast_to_group, name='broadcast_to_group'),
    path('api/broadcast-all/', views.broadcast_all, name='broadcast_all'),

    # ── Admin Messages ─────────────────────────────────────────────────────
    path('messages/', views.AdminMessagesView.as_view(), name='admin_messages'),
]
