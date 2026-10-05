from django.urls import path

app_name = 'reports'

from . import views

urlpatterns = [
    path('finance/', views.FinanceReportView.as_view(), name='finance_report'),
    path('attendance/today/', views.TodayAttendanceView.as_view(), name='today_attendance'),
    path('attendance/today/<int:group_id>/', views.TodayAttendanceDetailView.as_view(), name='today_attendance_detail'),
]
