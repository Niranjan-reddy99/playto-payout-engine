from django.urls import path
from . import views

urlpatterns = [
    path('auth/login/', views.LoginView.as_view(), name='login'),
    path('auth/logout/', views.LogoutView.as_view(), name='logout'),
    path('balance/', views.BalanceView.as_view(), name='balance'),
    path('payouts/', views.PayoutListCreateView.as_view(), name='payouts'),
    path('payouts/<uuid:payout_id>/', views.PayoutDetailView.as_view(), name='payout-detail'),
    path('ledger/', views.LedgerView.as_view(), name='ledger'),
]
