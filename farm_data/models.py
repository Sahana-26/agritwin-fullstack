from django.contrib.auth.models import User
from django.db import models


class FarmerProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='farmer_profile')
    full_name = models.CharField(max_length=150, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    village = models.CharField(max_length=150, blank=True)
    district = models.CharField(max_length=150, blank=True)
    state = models.CharField(max_length=150, blank=True)

    def __str__(self):
        return self.full_name or self.user.username


class FarmPlot(models.Model):
    farmer = models.ForeignKey(FarmerProfile, on_delete=models.CASCADE, related_name='plots')
    name = models.CharField(max_length=150)
    village = models.CharField(max_length=150, blank=True, null=True)
    latitude = models.FloatField(blank=True, null=True)
    longitude = models.FloatField(blank=True, null=True)
    area_acres = models.FloatField(blank=True, null=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.farmer} - {self.name}"


class CropProfile(models.Model):
    plot = models.ForeignKey(FarmPlot, on_delete=models.CASCADE, related_name='crop_profiles')
    crop_name = models.CharField(max_length=100)

    soil_ph = models.FloatField()
    organic_carbon = models.FloatField()
    fertilizer = models.FloatField()
    irrigation_frequency = models.FloatField()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('plot', 'crop_name')
        ordering = ['crop_name', 'plot__name']

    def __str__(self):
        return f"{self.plot.name} - {self.crop_name}"


class YieldPredictionHistory(models.Model):
    farmer = models.ForeignKey(
        FarmerProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='yield_predictions',
    )
    plot = models.ForeignKey(
        FarmPlot,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='yield_predictions',
    )

    crop_name = models.CharField(max_length=100)

    rainfall = models.FloatField()
    temperature = models.FloatField()
    soil_ph = models.FloatField()
    fertilizer = models.FloatField()
    irrigation_frequency = models.FloatField()
    organic_carbon = models.FloatField()

    predicted_yield = models.FloatField()
    unit = models.CharField(max_length=50, default='kg/ha')

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.crop_name} - {self.predicted_yield} {self.unit}"
    

class DataCollectionPoint(models.Model):
    farmer = models.ForeignKey(
        FarmerProfile,
        on_delete=models.CASCADE,
        related_name='collection_points'
    )
    name = models.CharField(max_length=150)
    issue = models.CharField(max_length=200)
    notes = models.TextField(blank=True)
    latitude = models.FloatField()
    longitude = models.FloatField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} - {self.issue}"