from django.urls import path
from django.contrib.auth.views import LogoutView

from . import views

app_name = 'users1'

urlpatterns = [
    path('', views.index, name='index'),
    path('login/', views.RoleLoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('teacher/', views.TeacherDashboardView.as_view(), name='teacher_dashboard'),
    path('admin/', views.AdminDashboardView.as_view(), name='admin_dashboard'),
]
