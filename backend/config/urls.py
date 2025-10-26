from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/banks/', include('banks.urls')),
    path('api/accounts/', include('accounts.urls')),
    path('api/reports/', include('reports.urls')),
]
