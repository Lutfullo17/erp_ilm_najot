from django.urls import path
from . import views

app_name = 'groups_app'

urlpatterns = [
    path('', views.GroupListView.as_view(), name='group_list'),
    path('<int:pk>/', views.GroupDetailView.as_view(), name='group_detail'),
    path('new/', views.GroupCreateView.as_view(), name='group_create'),
    path('<int:pk>/edit/', views.GroupUpdateView.as_view(), name='group_edit'),
    path('<int:pk>/add-student/', views.add_student_to_group, name='add_student'),
]
