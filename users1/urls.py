from django.urls import path
from django.contrib.auth.views import LogoutView

from . import views

app_name = 'users1'

urlpatterns = [
    path('', views.index, name='index'),
    path('login/', views.RoleLoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('teacher/', views.TeacherDashboardView.as_view(), name='teacher_dashboard'),
    path('teacher/groups/', views.TeacherGroupsView.as_view(), name='teacher_groups'),
    path('teacher/messages/', views.TeacherMessagesView.as_view(), name='teacher_messages'),
    path('teacher/schedule/', views.TeacherScheduleView.as_view(), name='teacher_schedule'),
    path('teacher/profile/', views.TeacherProfileView.as_view(), name='teacher_profile'),
    path('admin/', views.AdminDashboardView.as_view(), name='admin_dashboard'),
    path('api/reply/<int:appeal_id>/', views.reply_appeal, name='reply_appeal'),
    path('api/resolve/<int:appeal_id>/', views.resolve_appeal, name='resolve_appeal'),
    path('api/broadcast/', views.broadcast_to_group, name='broadcast_to_group'),
    path('teachers/', views.TeacherListView.as_view(), name='teacher_list'),
    path('teachers/new/', views.TeacherCreateView.as_view(), name='teacher_create'),
    path('teachers/<int:pk>/edit/', views.TeacherUpdateView.as_view(), name='teacher_edit'),
    path('teachers/<int:pk>/delete/', views.delete_teacher, name='teacher_delete'),
]
