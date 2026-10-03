from django.urls import path

from . import views_home, views_misc, views_stub

app_name = 'new'

S = views_stub.coming_soon  # hali yozilmagan bo'limlar uchun vaqtinchalik

urlpatterns = [
    path('', views_home.HomeView.as_view(), name='home'),
    path('switch/<str:which>/', views_home.switch_ui, name='switch'),
    path('api/search/', views_misc.api_search, name='api_search'),
    path('feedback/', views_misc.feedback, name='feedback'),

    # --- vaqtinchalik (keyingi bosqichlarda almashtiriladi)
    path('payments/new/', S, name='pay'),
    path('payments/debtors/', S, name='debtors'),
    path('attendance/', S, name='attendance'),
    path('attendance/<int:gid>/', S, name='attendance_mark'),
    path('students/', S, name='students'),
    path('students/new/', S, name='student_new'),
    path('students/<int:pk>/', S, name='student'),
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
