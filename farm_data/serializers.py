from rest_framework import serializers
from .models import FarmerProfile, FarmPlot, CropProfile, YieldPredictionHistory, DataCollectionPoint


class FarmerProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    email = serializers.EmailField(source='user.email', read_only=True)

    class Meta:
        model = FarmerProfile
        fields = [
            'id',
            'username',
            'email',
            'full_name',
            'phone',
            'village',
            'district',
            'state',
        ]


class FarmPlotSerializer(serializers.ModelSerializer):
    farmer_id = serializers.IntegerField(source='farmer.id', read_only=True)
    farmer_name = serializers.CharField(source='farmer.full_name', read_only=True)

    class Meta:
        model = FarmPlot
        fields = [
            'id',
            'name',
            'village',
            'latitude',
            'longitude',
            'area_acres',
            'farmer_id',
            'farmer_name',
        ]


class CropProfileSerializer(serializers.ModelSerializer):
    plot_id = serializers.PrimaryKeyRelatedField(
        queryset=FarmPlot.objects.all(),
        source='plot'
    )
    plot_name = serializers.CharField(source='plot.name', read_only=True)
    farmer_id = serializers.IntegerField(source='plot.farmer.id', read_only=True)
    farmer_name = serializers.CharField(source='plot.farmer.full_name', read_only=True)

    class Meta:
        model = CropProfile
        fields = [
            'id',
            'crop_name',
            'soil_ph',
            'organic_carbon',
            'fertilizer',
            'irrigation_frequency',
            'plot_id',
            'plot_name',
            'farmer_id',
            'farmer_name',
            'created_at',
            'updated_at',
        ]


class YieldPredictionHistorySerializer(serializers.ModelSerializer):
    plot_name = serializers.CharField(source='plot.name', read_only=True)
    farmer_name = serializers.CharField(source='farmer.full_name', read_only=True)

    class Meta:
        model = YieldPredictionHistory
        fields = [
            'id',
            'farmer_name',
            'plot_name',
            'crop_name',
            'rainfall',
            'temperature',
            'soil_ph',
            'fertilizer',
            'irrigation_frequency',
            'organic_carbon',
            'predicted_yield',
            'unit',
            'created_at',
        ]

class DataCollectionPointSerializer(serializers.ModelSerializer):
    farmer_name = serializers.CharField(source='farmer.full_name', read_only=True)

    class Meta:
        model = DataCollectionPoint
        fields = [
            'id',
            'farmer_name',
            'name',
            'issue',
            'notes',
            'latitude',
            'longitude',
            'created_at',
        ]