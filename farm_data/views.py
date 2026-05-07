from django.db.models import Count
from django.shortcuts import get_object_or_404

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView

from .models import (
    FarmerProfile,
    FarmPlot,
    CropProfile,
    YieldPredictionHistory,
    DataCollectionPoint,
)
from .serializers import (
    FarmerProfileSerializer,
    FarmPlotSerializer,
    CropProfileSerializer,
    YieldPredictionHistorySerializer,
    DataCollectionPointSerializer,
)


def get_farmer_profile(user):
    profile, _ = FarmerProfile.objects.get_or_create(
        user=user,
        defaults={'full_name': user.username}
    )
    return profile


class FarmerMeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        profile = get_farmer_profile(request.user)
        serializer = FarmerProfileSerializer(profile)
        return Response(serializer.data)

    def patch(self, request):
        profile = get_farmer_profile(request.user)
        serializer = FarmerProfileSerializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def put(self, request):
        profile = get_farmer_profile(request.user)
        serializer = FarmerProfileSerializer(profile, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class SummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        profile = get_farmer_profile(request.user)

        total_plots = FarmPlot.objects.filter(farmer=profile).count()
        total_crop_profiles = CropProfile.objects.filter(plot__farmer=profile).count()
        total_unique_crops = CropProfile.objects.filter(plot__farmer=profile).values('crop_name').distinct().count()
        total_predictions = YieldPredictionHistory.objects.filter(farmer=profile).count()

        return Response({
            'total_plots': total_plots,
            'total_crop_profiles': total_crop_profiles,
            'total_unique_crops': total_unique_crops,
            'total_predictions': total_predictions,
        })


class FarmPlotListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        profile = get_farmer_profile(request.user)
        plots = FarmPlot.objects.filter(farmer=profile)
        serializer = FarmPlotSerializer(plots, many=True)
        return Response(serializer.data)

    def post(self, request):
        profile = get_farmer_profile(request.user)
        serializer = FarmPlotSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(farmer=profile)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class FarmPlotDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, request, pk):
        profile = get_farmer_profile(request.user)
        return get_object_or_404(FarmPlot, pk=pk, farmer=profile)

    def patch(self, request, pk):
        plot = self.get_object(request, pk)
        serializer = FarmPlotSerializer(plot, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, pk):
        plot = self.get_object(request, pk)
        plot.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CropProfileListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        profile = get_farmer_profile(request.user)
        queryset = CropProfile.objects.filter(plot__farmer=profile)

        crop_name = request.query_params.get('crop_name')
        plot_id = request.query_params.get('plot_id')

        if crop_name:
            queryset = queryset.filter(crop_name__iexact=crop_name)

        if plot_id:
            queryset = queryset.filter(plot_id=plot_id)

        serializer = CropProfileSerializer(queryset, many=True)
        return Response(serializer.data)

    def post(self, request):
        profile = get_farmer_profile(request.user)
        serializer = CropProfileSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        plot = serializer.validated_data['plot']
        if plot.farmer_id != profile.id:
            return Response(
                {'message': 'This plot does not belong to the logged-in farmer'},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class CropProfileDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, request, pk):
        profile = get_farmer_profile(request.user)
        return get_object_or_404(CropProfile, pk=pk, plot__farmer=profile)

    def patch(self, request, pk):
        obj = self.get_object(request, pk)
        serializer = CropProfileSerializer(obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        plot = serializer.validated_data.get('plot', obj.plot)
        if plot.farmer_id != get_farmer_profile(request.user).id:
            return Response(
                {'message': 'This plot does not belong to the logged-in farmer'},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer.save()
        return Response(serializer.data)

    def delete(self, request, pk):
        obj = self.get_object(request, pk)
        obj.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MyCropsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        profile = get_farmer_profile(request.user)

        rows = (
            CropProfile.objects
            .filter(plot__farmer=profile)
            .values('crop_name')
            .annotate(plots_count=Count('plot', distinct=True))
            .order_by('crop_name')
        )

        data = [
            {
                'id': row['crop_name'].lower(),
                'plots_count': row['plots_count'],
            }
            for row in rows
        ]
        return Response(data)


class YieldHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        profile = get_farmer_profile(request.user)
        queryset = YieldPredictionHistory.objects.filter(farmer=profile)

        crop_name = request.query_params.get('crop_name')
        plot_id = request.query_params.get('plot_id')

        if crop_name:
            queryset = queryset.filter(crop_name__iexact=crop_name)

        if plot_id:
            queryset = queryset.filter(plot_id=plot_id)

        serializer = YieldPredictionHistorySerializer(queryset[:20], many=True)
        return Response(serializer.data)
    
class DataCollectionPointListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        profile = get_farmer_profile(request.user)
        points = DataCollectionPoint.objects.filter(farmer=profile)
        serializer = DataCollectionPointSerializer(points, many=True)
        return Response(serializer.data)

    def post(self, request):
        profile = get_farmer_profile(request.user)
        serializer = DataCollectionPointSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(farmer=profile)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class DataCollectionPointDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, request, pk):
        profile = get_farmer_profile(request.user)
        return get_object_or_404(DataCollectionPoint, pk=pk, farmer=profile)

    def delete(self, request, pk):
        point = self.get_object(request, pk)
        point.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)