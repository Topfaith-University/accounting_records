from django.urls import path, re_path
from . import views

urlpatterns = [
    path('', views.index, name='accounts_index'),
    path('create/', views.create_account, name='create_account'),
    path('all/', views.get_all_accounts, name='get_all_accounts'),
    path('types/', views.get_all_account_types, name='get_all_account_types'),
    re_path('^get_account/?$',
            views.get_account_by_id, name='get_account_by_id'),
]
