from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser
from .serializers import PredictionRequestSerializer
from .services.inference import MODEL_REGISTRY, predict_image, get_yield_estimation

class CropListView(APIView):
    def get(self, request):
        crops = [
            {"key": "coffee", "label": "Coffee"},
            {"key": "wheat", "label": "wheat"},
            {"key": "potato", "label": "potato"},
        ]
        return Response(crops, status=status.HTTP_200_OK)

class PredictView(APIView):
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        serializer = PredictionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        crop = serializer.validated_data["crop"].lower().strip()
        image = serializer.validated_data["image"]

        if crop not in MODEL_REGISTRY:
            return Response(
                {"message": f"Model not available for crop '{crop}'"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            result = predict_image(image, crop)
            print(result)

            recommendation = None
            severity = "Moderate"

            if crop == "coffee":
                prediction = result["prediction"].lower()
                if prediction == "healthy":
                    recommendation = "Leaf appears healthy. Continue routine monitoring."
                    severity = "Low"
                elif prediction == "rust":
                    recommendation = "Inspect nearby leaves, isolate spread if needed, and consult treatment guidance."
                    severity = "High"
                elif prediction == "phoma":
                    recommendation = "Check for affected regions and review moisture and fungal control measures."
                    severity = "Moderate"
                elif prediction == "miner":
                    recommendation = "Inspect leaf damage and consider pest management guidance."
                    severity = "Moderate"
                elif prediction == "cerscospora":
                    recommendation = "Review affected foliage and monitor disease spread closely."
                    severity = "Moderate"

            yield_estimation = get_yield_estimation(result["prediction"])

            return Response(
                {
                    "success": True,
                    "crop": crop.capitalize(),
                    "prediction": result["prediction"],
                    "confidence": result["confidence"],
                    "severity": severity,
                    "recommendation": recommendation,
                    "yield_estimation": yield_estimation,
                    "predicted_index": result["predicted_index"],
                    "scores": result["all_scores"],
                },
                status=status.HTTP_200_OK
            )

        except Exception as e:
            return Response(
                {"success": False, "message": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
