from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import BankAccountViewSet, BankReconciliationViewSet

router = DefaultRouter()
router.register('accounts', BankAccountViewSet, basename='bank-account')
router.register('reconciliations', BankReconciliationViewSet, basename='bank-reconciliation')

urlpatterns = [
    path('', include(router.urls)),
]
