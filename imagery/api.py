from shapely.geometry import Point
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import AnalysisRecord
from .constants import LAYER_BY_THEME
from .db_rasters import sample_layer_value
from .processing import load_aoi_shape
from .services import RUN_SUMMARY_TYPE, serialize_selection_record, build_selection_trend_payload
import os
import requests
from django.core.cache import cache
import json
from socket import timeout as SocketTimeout
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

class PublicAPIView(APIView):
    permission_classes = [AllowAny]

class UnifiedSelectionAPIView(PublicAPIView):
    def get(self, request):
        mode = request.GET.get("mode")
        theme = request.GET.get("theme")
        record_key = request.GET.get("record_key")
        catalog = str(request.GET.get("catalog", "")).lower() in {"1", "true", "yes"}

        if not mode:
            return Response({"detail": "mode is required"}, status=400)

        if mode == "future" and catalog:
            rows = AnalysisRecord.objects.filter(
                analysis_type=RUN_SUMMARY_TYPE,
                mode="future",
            ).order_by("start_date", "window_index", "record_key")

            results = []
            seen = set()

            for row in rows:
                if row.record_key in seen:
                    continue
                seen.add(row.record_key)
                results.append(
                    {
                        "record_key": row.record_key,
                        "window_label": row.window_label,
                        "start_date": row.start_date.isoformat(),
                        "end_date": row.end_date.isoformat(),
                        "year": row.year,
                        "season": row.season,
                        "window_index": row.window_index,
                        "status": row.status,
                    }
                )

            return Response(
                {
                    "selection": {
                        "mode": "future",
                        "catalog": True,
                    },
                    "count": len(results),
                    "results": results,
                }
            )

        if not theme:
            return Response({"detail": "theme is required"}, status=400)
        if not record_key:
            return Response({"detail": "record_key is required"}, status=400)

        if theme not in LAYER_BY_THEME:
            return Response({"detail": f"Unsupported theme: {theme}"}, status=400)

        rows = AnalysisRecord.objects.filter(
            analysis_type=RUN_SUMMARY_TYPE,
            mode=mode,
            record_key=record_key,
        ).order_by("start_date", "window_index", "record_key")

        results = [serialize_selection_record(row, theme) for row in rows]

        payload = {
            "selection": {
                "mode": mode,
                "record_key": record_key,
                "theme": theme,
            },
            "count": len(results),
            "results": results,
        }

        if mode == "historical" and results:
            season = results[0].get("season")
            if season:
                payload["trend"] = build_selection_trend_payload(season)

        return Response(payload)
        
class PixelSampleAPIView(PublicAPIView):
    TARGET_LAYERS = {
        "ndvi": "ndvi",
        "ndmi": "ndmi",
        "awei": "awei",
        "slope": "slope",
        "elevation": "dem",
    }

    def get(self, request):
        run_id = request.GET.get("run_id")
        lat = request.GET.get("lat")
        lng = request.GET.get("lng") or request.GET.get("lon")
        theme = request.GET.get("theme")

        if not run_id:
            return Response({"detail": "run_id is required"}, status=400)
        if lat is None:
            return Response({"detail": "lat is required"}, status=400)
        if lng is None:
            return Response({"detail": "lng is required"}, status=400)

        try:
            lat = float(lat)
            lng = float(lng)
        except ValueError:
            return Response({"detail": "lat/lng must be numeric"}, status=400)

        current_analysis_type = None
        if theme:
            current_analysis_type = LAYER_BY_THEME.get(theme)
            if not current_analysis_type:
                return Response({"detail": f"Unsupported theme: {theme}"}, status=400)

        point = Point(lng, lat)
        inside_aoi = load_aoi_shape().covers(point)

        values = {key: None for key in self.TARGET_LAYERS.keys()}
        current_layer = {
            "theme": theme,
            "analysis_type": current_analysis_type,
            "value": None,
        }

        if inside_aoi:
            requested_types = set(self.TARGET_LAYERS.values())
            if current_analysis_type:
                requested_types.add(current_analysis_type)

            rows = AnalysisRecord.objects.filter(
                run_id=run_id,
                status="ready",
                analysis_type__in=list(requested_types),
            ).only("id", "analysis_type")

            rows_by_type = {row.analysis_type: row for row in rows}

            for response_key, analysis_type in self.TARGET_LAYERS.items():
                row = rows_by_type.get(analysis_type)
                if not row:
                    continue
                value = sample_layer_value(row.id, lng, lat, band=1)
                values[response_key] = float(value) if value is not None else None

            if current_analysis_type:
                row = rows_by_type.get(current_analysis_type)
                if row:
                    value = sample_layer_value(row.id, lng, lat, band=1)
                    current_layer["value"] = float(value) if value is not None else None

        return Response(
            {
                "run_id": str(run_id),
                "lat": lat,
                "lng": lng,
                "inside_aoi": inside_aoi,
                "has_any_value": any(v is not None for v in values.values()) or current_layer["value"] is not None,
                "values": values,
                "current_layer": current_layer,
            }
        )

        
class AOILiveConditionsAPIView(PublicAPIView):
    WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
    AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
    TIMEOUT_SECONDS = 12

    def _fetch_json(self, base_url, params):
        url = f"{base_url}?{urlencode(params)}"
        with urlopen(url, timeout=self.TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))

    def get(self, request):
        aoi = load_aoi_shape()
        centroid = aoi.centroid

        lat = float(centroid.y)
        lng = float(centroid.x)

        weather_payload = {}
        air_payload = {}
        weather_error = None
        air_error = None

        try:
            weather_payload = self._fetch_json(
                self.WEATHER_URL,
                {
                    "latitude": lat,
                    "longitude": lng,
                    "current": "temperature_2m,rain,precipitation,wind_speed_10m",
                    "timezone": "auto",
                },
            )
        except (HTTPError, URLError, SocketTimeout, ValueError) as exc:
            weather_error = str(exc)

        try:
            air_payload = self._fetch_json(
                self.AIR_QUALITY_URL,
                {
                    "latitude": lat,
                    "longitude": lng,
                    "current": "us_aqi",
                    "timezone": "auto",
                },
            )
        except (HTTPError, URLError, SocketTimeout, ValueError) as exc:
            air_error = str(exc)

        weather_current = weather_payload.get("current", {})
        weather_units = weather_payload.get("current_units", {})
        air_current = air_payload.get("current", {})
        air_units = air_payload.get("current_units", {})

        temperature_value = weather_current.get("temperature_2m")
        rain_value = weather_current.get("rain")
        if rain_value is None:
            rain_value = weather_current.get("precipitation")
        wind_speed_value = weather_current.get("wind_speed_10m")
        aqi_value = air_current.get("us_aqi")

        response_payload = {
            "centroid": {
                "lat": lat,
                "lng": lng,
            },
            "temperature": {
                "value": float(temperature_value) if temperature_value is not None else None,
                "unit": weather_units.get("temperature_2m", "°C"),
                "time": weather_current.get("time"),
            },
            "rainfall": {
                "value": float(rain_value) if rain_value is not None else None,
                "unit": weather_units.get("rain") or weather_units.get("precipitation", "mm"),
                "time": weather_current.get("time"),
            },
            "wind_speed": {
                "value": float(wind_speed_value) if wind_speed_value is not None else None,
                "unit": weather_units.get("wind_speed_10m", "km/h"),
                "time": weather_current.get("time"),
            },
            "aqi": {
                "value": float(aqi_value) if aqi_value is not None else None,
                "unit": air_units.get("us_aqi", ""),
                "time": air_current.get("time"),
            },
            "errors": {
                "temperature": weather_error,
                "rainfall": weather_error,
                "wind_speed": weather_error,
                "aqi": air_error,
            },
        }

        status_code = 200 if (
            temperature_value is not None
            or rain_value is not None
            or wind_speed_value is not None
            or aqi_value is not None
        ) else 502
        return Response(response_payload, status=status_code)