from django.urls import path
from . import views

app_name = 'groups_app'

urlpatterns = [
    path('', views.GroupListView.as_view(), name='group_list'),
    path('<int:pk>/', views.GroupDetailView.as_view(), name='group_detail'),
    path('new/', views.GroupCreateView.as_view(), name='group_create'),
    path('<int:pk>/edit/', views.GroupUpdateView.as_view(), name='group_edit'),
    path('<int:pk>/add-student/', views.add_student_to_group, name='add_student'),
    path('<int:pk>/remove-student/<int:student_pk>/', views.remove_student_from_group, name='remove_student'),
    path('<int:pk>/delete/', views.delete_group, name='group_delete'),
    path('<int:pk>/toggle-pause/', views.toggle_pause_group, name='group_toggle_pause'),
    path('rooms/', views.RoomAvailabilityView.as_view(), name='room_availability'),
    path('<int:group_pk>/edit-lesson/<str:target_day>/', views.admin_edit_lesson_page, name='admin_edit_lesson_page'),
    path('<int:group_pk>/edit-lesson/<str:target_day>/save/', views.admin_edit_lesson, name='admin_edit_lesson_save'),
    path('student/<int:student_pk>/add-to-group/', views.add_student_to_group_modal, name='add_student_to_group_modal'),
]
