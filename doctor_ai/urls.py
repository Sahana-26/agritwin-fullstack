from django.urls import path
from .views import CropListView, PredictView

urlpatterns = [
    path("crops/", CropListView.as_view(), name="doctor-crops"),
    path("predict/", PredictView.as_view(), name="doctor-predict"),
]