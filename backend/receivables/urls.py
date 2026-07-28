from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CustomerViewSet, SalesInvoiceViewSet

router = DefaultRouter()
router.register('customers', CustomerViewSet, basename='customer')
router.register('invoices', SalesInvoiceViewSet, basename='sales-invoice')

urlpatterns = [
    path('', include(router.urls)),
]
