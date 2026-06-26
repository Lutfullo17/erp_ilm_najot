from django.urls import path
from . import views

app_name = 'payments'

urlpatterns = [
    path('', views.PaymentListView.as_view(), name='payment_list'),
    path('new/', views.PaymentCreateView.as_view(), name='payment_create'),
    path('debtors/', views.DebtorListView.as_view(), name='debtor_list'),
    path('api/search/', views.api_search_students, name='api_search_students'),
    path('api/student-balance/<int:student_id>/<int:group_id>/', views.student_balance, name='api_student_balance'),
    path('api/create/', views.create_payment, name='api_create_payment'),
]
