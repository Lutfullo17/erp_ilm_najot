from django.urls import path
from . import views

app_name = 'reports'

urlpatterns = [
    path('export/students/', views.ExportStudentsView.as_view(), name='export_students'),
    path('export/payments/', views.ExportPaymentsView.as_view(), name='export_payments'),
    path('export/attendance/', views.ExportAttendanceView.as_view(), name='export_attendance'),
]
