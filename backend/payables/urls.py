from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import VendorViewSet, PurchaseInvoiceViewSet

router = DefaultRouter()
router.register('vendors', VendorViewSet, basename='vendor')
router.register('invoices', PurchaseInvoiceViewSet, basename='purchase-invoice')

urlpatterns = [
    path('', include(router.urls)),
]
