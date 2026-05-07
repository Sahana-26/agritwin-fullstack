from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v2/", include("imagery.api_urls")),
    path("", include("imagery.urls")),
    path('api/accounts/', include('accounts.urls')),
    path('api/doctor_ai/', include('doctor_ai.urls')),
    path('api/farm_data/', include('farm_data.urls')),
    path('api/yield_ai/', include('yield_ai.urls')),
]