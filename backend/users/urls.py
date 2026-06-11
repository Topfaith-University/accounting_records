from django.urls import path
from . import views

urlpatterns = [
    path('invite-codes/', views.invite_codes),
    path('invite-codes/<int:pk>/', views.revoke_invite_code),
]
