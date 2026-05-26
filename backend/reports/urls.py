from django.urls import path
from . import views

urlpatterns = [
    path('trial-balance/', views.trial_balance, name='trial-balance'),
    path('income-statement/', views.income_statement, name='income-statement'),
    path('balance-sheet/', views.balance_sheet, name='balance-sheet'),
    path('gl-detail/', views.gl_detail, name='gl-detail'),
    path('dashboard/', views.dashboard, name='dashboard'),
]
