from django.urls import path
from . import views

app_name = 'payments'

urlpatterns = [
    path('', views.PaymentListView.as_view(), name='payment_list'),
    path('new/', views.PaymentCreateView.as_view(), name='payment_create'),
    path('debtors/', views.DebtorListView.as_view(), name='debtor_list'),
    path('debtors/group/<int:group_id>/', views.GroupDebtorView.as_view(), name='group_debtor_list'),
    path('api/search/', views.api_search_students, name='api_search_students'),
    path('api/student/<int:student_id>/', views.api_get_student_for_payment, name='api_get_student_for_payment'),
    path('api/student-all-debts/<int:student_id>/', views.api_student_all_debts, name='api_student_all_debts'),
    path('api/student-balance/<int:student_id>/<int:group_id>/', views.student_balance, name='api_student_balance'),
    path('api/create/', views.create_payment, name='api_create_payment'),
    path('delete/<int:pk>/', views.delete_payment_view, name='delete_payment'),
]
