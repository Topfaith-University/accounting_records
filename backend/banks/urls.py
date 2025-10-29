from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='banks_index'),
    path('create/', views.create_bank_account, name='create_bank_account'),
]
