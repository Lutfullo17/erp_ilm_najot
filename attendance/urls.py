from django.urls import path
from . import views

app_name = 'attendance'

urlpatterns = [
    path('mark/<int:group_id>/', views.AttendanceMarkView.as_view(), name='attendance_mark'),
    path('api/save-lesson-plan/', views.save_lesson_plan, name='save_lesson_plan'),
]
