from django.urls import path
from .api import UnifiedSelectionAPIView, PixelSampleAPIView, AOILiveConditionsAPIView

urlpatterns = [
    path("analysis/selection/", UnifiedSelectionAPIView.as_view(), name="analysis-selection"),
    path("analysis/pixel-sample/", PixelSampleAPIView.as_view(), name="analysis-pixel-sample"),
    path("live/aoi-conditions/", AOILiveConditionsAPIView.as_view(), name="aoi-live-conditions"),
]