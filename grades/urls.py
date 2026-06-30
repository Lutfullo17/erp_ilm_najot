from django.urls import path

from . import views

app_name = 'grades'

urlpatterns = [
    path('', views.index, name='index'),
    path('input/', views.GradeInputView.as_view(), name='grade_input'),
    path('list/', views.TeacherGradeListView.as_view(), name='grade_list'),
    path('teacher/groups/', views.teacher_groups, name='teacher_groups'),
    path('teacher/groups/<int:group_id>/', views.group_grades, name='group_grades'),
]
