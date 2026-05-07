from django.urls import path
from .views import home_view, crops_view, coconut_view

urlpatterns = [
    path("", home_view, name="home"),
    path("crops/", crops_view, name="crops"),
    path("coconut/", coconut_view, name="coconut"),
]