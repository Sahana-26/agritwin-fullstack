from django.urls import path
from .views import (
    FarmerMeView,
    SummaryView,
    FarmPlotListCreateView,
    FarmPlotDetailView,
    CropProfileListCreateView,
    CropProfileDetailView,
    MyCropsView,
    YieldHistoryView,
    DataCollectionPointListCreateView,
    DataCollectionPointDetailView,
)

urlpatterns = [
    path('me/', FarmerMeView.as_view(), name='farmer-me'),
    path('summary/', SummaryView.as_view(), name='farmer-summary'),

    path('plots/', FarmPlotListCreateView.as_view(), name='plot-list-create'),
    path('plots/<int:pk>/', FarmPlotDetailView.as_view(), name='plot-detail'),

    path('crop-profiles/', CropProfileListCreateView.as_view(), name='crop-profile-list-create'),
    path('crop-profiles/<int:pk>/', CropProfileDetailView.as_view(), name='crop-profile-detail'),

    path('my-crops/', MyCropsView.as_view(), name='my-crops'),
    path('yield-history/', YieldHistoryView.as_view(), name='yield-history'),

    path('collection-points/', DataCollectionPointListCreateView.as_view(), name='collection-points'),
    path('collection-points/<int:pk>/', DataCollectionPointDetailView.as_view(), name='collection-point-detail'),
]