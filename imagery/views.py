from django.shortcuts import render
from .aoi import load_aoi_feature


def home_view(request):
    return render(request, "imagery/home.html")


def crops_view(request):
    return render(request, "imagery/crops.html")


def coconut_view(request):
    return render(
        request,
        "imagery/coconut.html",
        {
            "aoi_geojson": load_aoi_feature(),
        },
    )