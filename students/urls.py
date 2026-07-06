from django.urls import path
from . import views

app_name = 'students'

urlpatterns = [
    path('', views.StudentListView.as_view(), name='student_list'),
    path('<int:pk>/', views.StudentDetailView.as_view(), name='student_detail'),
    path('new/', views.StudentCreateView.as_view(), name='student_create'),
    path('<int:pk>/edit/', views.StudentUpdateView.as_view(), name='student_edit'),
    path('<int:pk>/delete/', views.delete_student, name='student_delete'),
    path('api/check-parent-phone/', views.check_parent_phone, name='check_parent_phone'),
    path('api/<int:pk>/debt/', views.get_student_debt, name='student_debt'),
]

