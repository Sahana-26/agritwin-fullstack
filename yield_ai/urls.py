from django.urls import path
from .views import YieldPredictionView

urlpatterns = [
    path('predict/', YieldPredictionView.as_view(), name='yield-predict'),
]