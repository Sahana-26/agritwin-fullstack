from django.shortcuts import get_object_or_404

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView

from farm_data.models import FarmerProfile, FarmPlot, YieldPredictionHistory
from .serializers import YieldPredictionRequestSerializer
from .services.inference import MODEL_REGISTRY, predict_yield


def get_farmer_profile(user):
    profile, _ = FarmerProfile.objects.get_or_create(
        user=user,
        defaults={'full_name': user.username}
    )
    return profile


class YieldPredictionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = YieldPredictionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        validated = serializer.validated_data
        crop_key = validated['crop'].lower().strip()

        if crop_key not in MODEL_REGISTRY:
            return Response(
                {'success': False, 'message': f"Model not available for crop '{crop_key}'"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        farmer_profile = get_farmer_profile(request.user)
        plot = get_object_or_404(FarmPlot, pk=validated['plot_id'], farmer=farmer_profile)

        try:
            predicted_yield = predict_yield(crop_key, validated)

            YieldPredictionHistory.objects.create(
                farmer=farmer_profile,
                plot=plot,
                crop_name=MODEL_REGISTRY[crop_key]['label'],
                rainfall=validated['rainfall'],
                temperature=validated['temperature'],
                soil_ph=validated['soil_ph'],
                fertilizer=validated['fertilizer'],
                irrigation_frequency=validated['irrigation_frequency'],
                organic_carbon=validated['organic_carbon'],
                predicted_yield=predicted_yield,
                unit='kg/ha',
            )

            return Response(
                {
                    'success': True,
                    'crop': MODEL_REGISTRY[crop_key]['label'],
                    'plot_name': plot.name,
                    'predicted_yield': predicted_yield,
                    'unit': 'kg/ha',
                },
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            return Response(
                {'success': False, 'message': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        
