from django.urls import path

from . import views_att, views_home, views_misc, views_pay, views_students, views_stub

app_name = 'new'

S = views_stub.coming_soon  # hali yozilmagan bo'limlar uchun vaqtinchalik

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

    # --- vaqtinchalik (keyingi bosqichlarda almashtiriladi)
    path('attendance/', views_att.AttendanceListView.as_view(), name='attendance'),
    path('attendance/<int:gid>/', views_att.AttendanceMarkView.as_view(), name='attendance_mark'),
    path('api/attendance/<int:gid>/', views_att.api_attendance, name='api_attendance'),
    path('students/', views_students.StudentsView.as_view(), name='students'),
    path('students/new/', views_students.StudentNewView.as_view(), name='student_new'),
    path('students/<int:pk>/', views_students.StudentDetailView.as_view(), name='student'),
    path('students/<int:pk>/edit/', views_students.StudentEditView.as_view(), name='student_edit'),
    path('students/<int:pk>/delete/', views_students.student_delete, name='student_delete'),
    path('api/students/<int:pk>/group/', views_students.api_student_group, name='api_student_group'),
    path('groups/', S, name='groups'),
    path('groups/new/', S, name='group_new'),
    path('groups/<int:pk>/', S, name='group'),
    path('schedule/', S, name='schedule'),
    path('messages/', S, name='messages'),
    path('staff/', S, name='staff'),
    path('staff/teachers/<int:pk>/', S, name='staff_teacher'),
    path('reports/', S, name='report'),
    path('settings/', S, name='settings'),
    path('profile/', S, name='profile'),
    path('grades/', S, name='grades'),
    path('my-groups/', S, name='my_groups'),
    path('my-groups/<int:pk>/', S, name='my_group'),
    path('my-schedule/', S, name='my_schedule'),
]
