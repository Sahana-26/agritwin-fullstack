from rest_framework import serializers

class PredictionRequestSerializer(serializers.Serializer):
    crop = serializers.CharField()
    image = serializers.ImageField()