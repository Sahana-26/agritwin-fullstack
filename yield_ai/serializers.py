from rest_framework import serializers


class YieldPredictionRequestSerializer(serializers.Serializer):
    crop = serializers.CharField()
    plot_id = serializers.IntegerField()

    rainfall = serializers.FloatField()
    temperature = serializers.FloatField()
    soil_ph = serializers.FloatField()
    fertilizer = serializers.FloatField()
    irrigation_frequency = serializers.FloatField()
    organic_carbon = serializers.FloatField()