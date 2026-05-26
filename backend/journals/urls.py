from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import JournalEntryViewSet, FiscalYearViewSet, AccountingPeriodViewSet

router = DefaultRouter()
router.register('entries', JournalEntryViewSet, basename='journal-entry')
router.register('fiscal-years', FiscalYearViewSet, basename='fiscal-year')
router.register('periods', AccountingPeriodViewSet, basename='accounting-period')

urlpatterns = [
    path('', include(router.urls)),
]
