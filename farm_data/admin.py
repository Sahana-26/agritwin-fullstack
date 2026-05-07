from django.contrib import admin
from .models import FarmerProfile, FarmPlot, CropProfile, YieldPredictionHistory, DataCollectionPoint

admin.site.register(FarmerProfile)
admin.site.register(FarmPlot)
admin.site.register(CropProfile)
admin.site.register(YieldPredictionHistory)
admin.site.register(DataCollectionPoint)