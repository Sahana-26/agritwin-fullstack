from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.urls import reverse

from pyproj import CRS, Transformer
from rasterio.features import geometry_mask
from rasterio.transform import Affine
from shapely.geometry import mapping, shape
from shapely.ops import transform as shapely_transform

from .constants import LAYER_BY_THEME, LAYER_GUIDES, SEASONS, STYLE_CONFIGS, THEME_LABELS

from .db_rasters import array_to_gtiff_bytes, layer_extent_bounds, load_layer_array, read_layer_gtiff_bytes, upsert_layer_raster, render_layer_png
import base64
import uuid
from .models import AnalysisRecord
from .processing import compute_run_outputs, load_aoi_feature, load_aoi_shape
from rasterio.enums import Resampling
from rasterio.warp import reproject

import numpy as np


RUN_SUMMARY_TYPE = "summary"
from datetime import timedelta


def classify_window_year_season(start_date, end_date):
    midpoint = start_date + timedelta(days=((end_date - start_date).days // 2))
    return midpoint.year, infer_season_for_date(midpoint)

def stable_run_id(record_key: str):
    return uuid.uuid5(uuid.NAMESPACE_DNS, f"agritwin:{record_key}")


def infer_season_for_date(dt):
    month = dt.month
    if month in [2, 3, 4, 5]:
        return "Pre-Monsoon"
    if month in [6, 7, 8, 9]:
        return "Monsoon"
    if month in [10, 11]:
        return "Post-Monsoon"
    return "Winter"


def _truthy(value):
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}

THEME_BY_LAYER = {layer_name: theme for theme, layer_name in LAYER_BY_THEME.items()}

CLASS_SPECS = {
    'ndvi': [
        ('Bare / Very Low', -9999, 0.20),
        ('Low', 0.20, 0.35),
        ('Moderate', 0.35, 0.50),
        ('Healthy', 0.50, 0.70),
        ('Very Healthy', 0.70, 9999),
    ],
    'ndvi_anomaly': [
        ('Strong Decline', -9999, -0.10),
        ('Decline', -0.10, -0.02),
        ('Stable', -0.02, 0.02),
        ('Increase', 0.02, 0.10),
        ('Strong Increase', 0.10, 9999),
    ],
    'ndmi': [
        ('Dry', -9999, 0.00),
        ('Slightly Dry', 0.00, 0.10),
        ('Balanced', 0.10, 0.20),
        ('Moist', 0.20, 0.35),
        ('Wet', 0.35, 9999),
    ],
    'waterlite': [
        ('Very Low', -9999, 0.20),
        ('Low', 0.20, 0.40),
        ('Moderate', 0.40, 0.60),
        ('High', 0.60, 0.80),
        ('Very High', 0.80, 9999),
    ],
    'coconut': [
        ('Very Low', -9999, 0.20),
        ('Low', 0.20, 0.40),
        ('Moderate', 0.40, 0.60),
        ('High', 0.60, 0.80),
        ('Very High', 0.80, 9999),
    ],
    'pepper': [
        ('Very Low', -9999, 0.20),
        ('Low', 0.20, 0.40),
        ('Moderate', 0.40, 0.60),
        ('High', 0.60, 0.80),
        ('Very High', 0.80, 9999),
    ],
    'mudcottage': [
        ('Very Low', -9999, 0.20),
        ('Low', 0.20, 0.40),
        ('Moderate', 0.40, 0.60),
        ('High', 0.60, 0.80),
        ('Very High', 0.80, 9999),
    ],
    'sandalwood': [
        ('Very Low', -9999, 0.20),
        ('Low', 0.20, 0.40),
        ('Moderate', 0.40, 0.60),
        ('High', 0.60, 0.80),
        ('Very High', 0.80, 9999),
    ],
    'waterharvesting': [
        ('Very Low', -9999, 0.20),
        ('Low', 0.20, 0.40),
        ('Moderate', 0.40, 0.60),
        ('High', 0.60, 0.80),
        ('Very High', 0.80, 9999),
    ],
    'slope': [
        ('Flat', -9999, 5),
        ('Gentle', 5, 10),
        ('Moderate', 10, 20),
        ('Steep', 20, 30),
        ('Very Steep', 30, 9999),
    ],
}


def season_window(year: int, season_name: str):
    season = SEASONS[season_name]
    sm, sd = season['start']
    em, ed = season['end']
    start = date(year, sm, sd)
    end_year = year + 1 if season_name == 'Winter' else year
    end = date(end_year, em, ed)
    return start, end


def historical_run_specs():
    specs = []
    for year in range(settings.HISTORICAL_START_YEAR, settings.HISTORICAL_END_YEAR + 1):
        for season_name in SEASONS.keys():
            start, end = season_window(year, season_name)
            specs.append(
                {
                    'mode': 'historical',
                    'year': year,
                    'season': season_name,
                    'start_date': start,
                    'end_date': end,
                    'record_key': f"historical_{year}_{season_name.lower().replace('-', '_').replace(' ', '_')}",
                }
            )
    return specs

def future_run_specs(until_date: date):
    specs = []
    cursor = settings.FUTURE_START_DATE
    idx = 1

    while cursor <= until_date:
        window_end = min(cursor + timedelta(days=9), until_date)
        year, season = classify_window_year_season(cursor, window_end)

        specs.append(
            {
                "mode": "future",
                "year": year,
                "season": season,
                "window_index": idx,
                "window_label": f"{cursor.isoformat()} to {window_end.isoformat()}",
                "start_date": cursor,
                "end_date": window_end,
                "record_key": f"future_{cursor.isoformat()}_{window_end.isoformat()}",
            }
        )

        cursor = window_end + timedelta(days=1)
        idx += 1

    return specs


def completed_future_run_specs(until_date: date):
    specs = future_run_specs(until_date)
    return [
        spec
        for spec in specs
        if (spec["end_date"] - spec["start_date"]).days == 9
    ]

def get_or_create_run(spec: dict) -> AnalysisRecord:
    run_id = stable_run_id(spec["record_key"])
    defaults = {
        "record_key": spec["record_key"],
        "mode": spec["mode"],
        "year": spec.get("year"),
        "season": spec.get("season"),
        "window_index": spec.get("window_index"),
        "window_label": spec.get("window_label"),
        "start_date": spec["start_date"],
        "end_date": spec["end_date"],
        "status": "pending",
        "source_sensor": "UNAVAILABLE",
        "source_collection": "",
        "fallback_used": False,
        "cloud_threshold": settings.SENTINEL2_CLOUD_THRESHOLD,
        "mean_cloud_cover": None,
        "valid_pixel_fraction": 0.0,
        "confidence": "",
        "selected_item_ids": [],
        "summary_cards": {},
        "run_stats": {},
        "notes": "",
        "mean_ndvi": None,
        "mean_ndmi": None,
        "mean_awei": None,
        "srid": 4326,
        "width": 0,
        "height": 0,
        "band_count": 1,
        "nodata": None,
        "min_value": None,
        "max_value": None,
        "style_config": {},
        "stats": {},
    }
    record, _ = AnalysisRecord.objects.update_or_create(
        run_id=run_id,
        analysis_type=RUN_SUMMARY_TYPE,
        defaults=defaults,
    )
    return record


def get_baseline_ndvi_for_run(run: AnalysisRecord):
    if run.mode != "historical":
        return None

    prior_rows = list(
        AnalysisRecord.objects.filter(
            mode="historical",
            season=run.season,
            year__lt=run.year,
            analysis_type="ndvi",
            status="ready",
        ).order_by("year")
    )
    if not prior_rows:
        return None

    arrays = []
    for row in prior_rows:
        arr, _, _, nodata = load_layer_array(row.id)
        band = arr[0].astype("float32")
        if nodata is not None:
            band = np.where(np.isclose(band, nodata), np.nan, band)
        arrays.append(band)

    return np.nanmean(np.stack(arrays, axis=0), axis=0).astype("float32")

def _force_2d_geom(geom):
    return shapely_transform(lambda x, y, z=None: (x, y), geom)


def _load_exact_aoi_shape():
    # always read the original AOI from the GeoJSON, not the buffered analysis geom
    return _force_2d_geom(shape(load_aoi_feature()['geometry']))


def _project_geom_to_crs(geom, dst_crs):
    src_crs = CRS.from_epsg(4326)
    dst_crs = CRS.from_user_input(dst_crs)
    if src_crs == dst_crs:
        return geom
    transformer = Transformer.from_crs(src_crs, dst_crs, always_xy=True)
    return shapely_transform(transformer.transform, geom)


def _stats_from_array(arr):
    single = arr[0] if arr.ndim == 3 else arr
    valid = np.isfinite(single)

    if not np.any(valid):
        return {
            'mean': None,
            'min': None,
            'max': None,
            'std': None,
            'median': None,
            'q25': None,
            'q75': None,
            'valid_pixels': 0,
        }

    return {
        'mean': float(np.nanmean(single)),
        'min': float(np.nanmin(single)),
        'max': float(np.nanmax(single)),
        'std': float(np.nanstd(single)),
        'median': float(np.nanmedian(single)),
        'q25': float(np.nanpercentile(single, 25)),
        'q75': float(np.nanpercentile(single, 75)),
        'valid_pixels': int(np.sum(valid)),
    }

def _force_2d_geom(geom):
    return shapely_transform(lambda x, y, z=None: (x, y), geom)


def _load_exact_aoi_shape():
    return _force_2d_geom(shape(load_aoi_feature()["geometry"]))


def _project_geom_to_crs(geom, dst_crs):
    src_crs = CRS.from_epsg(4326)
    dst_crs = CRS.from_user_input(dst_crs)
    if src_crs == dst_crs:
        return geom
    transformer = Transformer.from_crs(src_crs, dst_crs, always_xy=True)
    return shapely_transform(transformer.transform, geom)


def _clip_array_to_exact_aoi(arr, transform, crs):
    exact_geom = _project_geom_to_crs(_load_exact_aoi_shape(), crs)

    pixel_width = abs(float(transform.a))
    pixel_height = abs(float(transform.e))
    half_pixel = max(pixel_width, pixel_height) * 0.5

    # Slight outward buffer so edge pixels visually cover the AOI boundary
    clip_geom = exact_geom.buffer(half_pixel, cap_style=3, join_style=2)

    keep_mask = geometry_mask(
        [mapping(clip_geom)],
        out_shape=arr.shape[-2:],
        transform=transform,
        invert=True,
        all_touched=True,
    )

    if not np.any(keep_mask):
        return arr.astype("float32"), transform

    rows, cols = np.where(keep_mask)

    # keep one extra pixel ring so the stored raster footprint is not visually inset
    row0 = max(int(rows.min()) - 1, 0)
    row1 = min(int(rows.max()) + 2, arr.shape[-2])
    col0 = max(int(cols.min()) - 1, 0)
    col1 = min(int(cols.max()) + 2, arr.shape[-1])

    submask = keep_mask[row0:row1, col0:col1]

    if arr.ndim == 2:
        clipped = np.where(submask, arr[row0:row1, col0:col1], np.nan)
    else:
        clipped = np.where(submask[None, :, :], arr[:, row0:row1, col0:col1], np.nan)

    clipped_transform = transform * Affine.translation(col0, row0)
    return clipped.astype("float32"), clipped_transform


def _stats_from_array(arr):
    single = arr[0] if arr.ndim == 3 else arr
    valid = np.isfinite(single)

    if not np.any(valid):
        return {
            "mean": None,
            "min": None,
            "max": None,
            "std": None,
            "median": None,
            "q25": None,
            "q75": None,
            "valid_pixels": 0,
        }

    return {
        "mean": float(np.nanmean(single)),
        "min": float(np.nanmin(single)),
        "max": float(np.nanmax(single)),
        "std": float(np.nanstd(single)),
        "median": float(np.nanmedian(single)),
        "q25": float(np.nanpercentile(single, 25)),
        "q75": float(np.nanpercentile(single, 75)),
        "valid_pixels": int(np.sum(valid)),
    }

@transaction.atomic
def save_run_outputs(run: AnalysisRecord, outputs: dict):
    run.status = outputs["status"]
    run.source_sensor = outputs["source_sensor"]
    run.fallback_used = outputs["fallback_used"]
    run.source_collection = (
        settings.SENTINEL2_COLLECTION
        if outputs["source_sensor"] in {"S2", "S2_WITH_S1_SUPPORT"}
        else settings.SENTINEL1_COLLECTION
    ) if outputs["source_sensor"] != "UNAVAILABLE" else ""
    run.mean_cloud_cover = outputs.get("mean_cloud_cover")
    run.valid_pixel_fraction = outputs.get("valid_pixel_fraction") or 0.0
    run.confidence = outputs.get("confidence", "")
    run.selected_item_ids = outputs.get("selected_item_ids", [])
    run.summary_cards = outputs.get("summary_cards", {})
    run.run_stats = outputs.get("stats_cache", {})
    run.notes = ""

    metrics_cache = run.run_stats or {}
    run.mean_ndvi = (metrics_cache.get("ndvi") or {}).get("mean")
    run.mean_ndmi = (metrics_cache.get("ndmi") or {}).get("mean")
    run.mean_awei = (metrics_cache.get("awei") or {}).get("mean")
    run.save()

    # remove old raster rows for this run, keep only summary row
    AnalysisRecord.objects.filter(run_id=run.run_id).exclude(analysis_type=RUN_SUMMARY_TYPE).delete()

    if run.status != "ready":
        return run

    transform = outputs["transform"]
    crs = outputs["crs"]
    nodata = outputs["nodata"]

    for layer_name, arr in outputs["layers"].items():
        stored_arr, stored_transform = _clip_array_to_exact_aoi(arr, transform, crs)
        layer_stats = _stats_from_array(stored_arr)

        if stored_arr.ndim == 2:
            write_arr = np.where(np.isfinite(stored_arr), stored_arr, nodata).astype("float32")
            band_count = 1
            height, width = stored_arr.shape
            min_value = layer_stats.get("min")
            max_value = layer_stats.get("max")
        else:
            write_arr = np.where(np.isfinite(stored_arr), stored_arr, nodata).astype("float32")
            band_count = stored_arr.shape[0]
            height, width = stored_arr.shape[1], stored_arr.shape[2]
            min_value = float(np.nanmin(stored_arr[0])) if np.isfinite(stored_arr[0]).any() else None
            max_value = float(np.nanmax(stored_arr[0])) if np.isfinite(stored_arr[0]).any() else None

        row, _ = AnalysisRecord.objects.update_or_create(
            run_id=run.run_id,
            analysis_type=layer_name,
            defaults={
                "record_key": run.record_key,
                "mode": run.mode,
                "year": run.year,
                "season": run.season,
                "window_index": run.window_index,
                "window_label": run.window_label,
                "start_date": run.start_date,
                "end_date": run.end_date,
                "status": run.status,
                "source_sensor": run.source_sensor,
                "source_collection": run.source_collection,
                "fallback_used": run.fallback_used,
                "cloud_threshold": run.cloud_threshold,
                "mean_cloud_cover": run.mean_cloud_cover,
                "valid_pixel_fraction": run.valid_pixel_fraction,
                "confidence": run.confidence,
                "selected_item_ids": run.selected_item_ids,
                "summary_cards": run.summary_cards,
                "run_stats": run.run_stats,
                "notes": run.notes,
                "mean_ndvi": run.mean_ndvi,
                "mean_ndmi": run.mean_ndmi,
                "mean_awei": run.mean_awei,
                "srid": crs.to_epsg() or 4326,
                "width": width,
                "height": height,
                "band_count": band_count,
                "nodata": nodata,
                "min_value": min_value,
                "max_value": max_value,
                "style_config": STYLE_CONFIGS.get(layer_name, {}),
                "stats": layer_stats,
            },
        )

        gtiff_bytes = array_to_gtiff_bytes(
            write_arr,
            stored_transform,
            crs,
            nodata=nodata,
            dtype="float32",
        )
        upsert_layer_raster(row, gtiff_bytes)

    return run

import base64
from .models import AnalysisRecord
from .db_rasters import render_layer_png, read_layer_gtiff_bytes, layer_extent_bounds

RUN_SUMMARY_TYPE = "summary"


def serialize_selection_record(summary_row: AnalysisRecord, theme: str):
    layer_name = LAYER_BY_THEME.get(theme)
    if not layer_name:
        raise ValueError(f"Unsupported theme: {theme}")

    def build_overlay_payload(layer_row, *, theme_name=None):
        payload = {
            "available": False,
            "theme": theme_name,
            "analysis_type": layer_row.analysis_type if layer_row else None,
            "style_config": layer_row.style_config if layer_row else {},
            "stats": layer_row.stats if layer_row else {},
            "raster_preview_png_base64": None,
            "raster_gtiff_base64": None,
            "bounds": None,
            "width": layer_row.width if layer_row else 0,
            "height": layer_row.height if layer_row else 0,
            "band_count": layer_row.band_count if layer_row else 0,
            "nodata": layer_row.nodata if layer_row else None,
            "min_value": layer_row.min_value if layer_row else None,
            "max_value": layer_row.max_value if layer_row else None,
        }

        if not layer_row:
            return payload

        try:
            payload["bounds"] = layer_extent_bounds(layer_row.id)
        except Exception:
            payload["bounds"] = None

        try:
            png_bytes = render_layer_png(layer_row.id)
        except Exception:
            png_bytes = None

        try:
            tif_bytes = read_layer_gtiff_bytes(layer_row.id)
        except Exception:
            tif_bytes = None

        payload["raster_preview_png_base64"] = (
            base64.b64encode(png_bytes).decode("ascii") if png_bytes else None
        )
        payload["raster_gtiff_base64"] = (
            base64.b64encode(tif_bytes).decode("ascii") if tif_bytes else None
        )
        payload["available"] = bool(
            payload["raster_preview_png_base64"] and payload["bounds"]
        )
        return payload

    layer_row = AnalysisRecord.objects.filter(
        run_id=summary_row.run_id,
        analysis_type=layer_name,
    ).first()

    rgb_row = AnalysisRecord.objects.filter(
        run_id=summary_row.run_id,
        analysis_type="rgb",
    ).first()

    theme_payload = build_overlay_payload(layer_row, theme_name=theme)
    if not theme_payload["analysis_type"]:
        theme_payload["analysis_type"] = layer_name

    rgb_payload = build_overlay_payload(rgb_row)
    if not rgb_payload["analysis_type"]:
        rgb_payload["analysis_type"] = "rgb"

    return {
        "run_id": str(summary_row.run_id),
        "record_key": summary_row.record_key,
        "mode": summary_row.mode,
        "year": summary_row.year,
        "season": summary_row.season,
        "window_index": summary_row.window_index,
        "window_label": summary_row.window_label,
        "start_date": summary_row.start_date.isoformat(),
        "end_date": summary_row.end_date.isoformat(),
        "status": summary_row.status,
        "source_sensor": summary_row.source_sensor,
        "source_collection": summary_row.source_collection,
        "fallback_used": summary_row.fallback_used,
        "cloud_threshold": summary_row.cloud_threshold,
        "mean_cloud_cover": summary_row.mean_cloud_cover,
        "valid_pixel_fraction": summary_row.valid_pixel_fraction,
        "confidence": summary_row.confidence,
        "selected_item_ids": summary_row.selected_item_ids or [],
        "summary_cards": summary_row.summary_cards or {},
        "run_stats": summary_row.run_stats or {},
        "notes": summary_row.notes,
        "mean_ndvi": summary_row.mean_ndvi,
        "mean_ndmi": summary_row.mean_ndmi,
        "mean_awei": summary_row.mean_awei,
        "selected_theme": theme_payload,
        "rgb_overlay": rgb_payload,
    }

def serialize_layer_row(row: AnalysisRecord, include_preview=False, include_raster=False):
    payload = {
        "analysis_type": row.analysis_type,
        "bounds": layer_extent_bounds(row.id) if row.rast else None,
        "band_count": row.band_count,
        "srid": row.srid,
        "width": row.width,
        "height": row.height,
        "nodata": row.nodata,
        "min_value": row.min_value,
        "max_value": row.max_value,
        "style_config": row.style_config or {},
        "stats": row.stats or {},
    }

    if include_preview and row.rast:
        png = render_layer_png(row)
        payload["preview_png_base64"] = base64.b64encode(png).decode("ascii")

    if include_raster and row.rast:
        tif = read_layer_gtiff_bytes(row.id)
        payload["raster_gtiff_base64"] = base64.b64encode(tif).decode("ascii") if tif else None

    return payload


def serialize_run_summary(row: AnalysisRecord):
    return {
        "run_id": str(row.run_id),
        "record_key": row.record_key,
        "mode": row.mode,
        "year": row.year,
        "season": row.season,
        "window_index": row.window_index,
        "window_label": row.window_label,
        "start_date": row.start_date.isoformat(),
        "end_date": row.end_date.isoformat(),
        "status": row.status,
        "source_sensor": row.source_sensor,
        "source_collection": row.source_collection,
        "fallback_used": row.fallback_used,
        "cloud_threshold": row.cloud_threshold,
        "mean_cloud_cover": row.mean_cloud_cover,
        "valid_pixel_fraction": row.valid_pixel_fraction,
        "confidence": row.confidence,
        "selected_item_ids": row.selected_item_ids or [],
        "summary_cards": row.summary_cards or {},
        "run_stats": row.run_stats or {},
        "notes": row.notes,
        "mean_ndvi": row.mean_ndvi,
        "mean_ndmi": row.mean_ndmi,
        "mean_awei": row.mean_awei,
    }


def serialize_run_payload(summary_row: AnalysisRecord, include_preview=True, include_raster=False):
    rows = list(
        AnalysisRecord.objects.filter(run_id=summary_row.run_id).order_by("analysis_type")
    )
    layers = [
        serialize_layer_row(row, include_preview=include_preview, include_raster=include_raster)
        for row in rows
        if row.analysis_type != RUN_SUMMARY_TYPE
    ]
    payload = serialize_run_summary(summary_row)
    payload["layers"] = layers
    return payload

def process_run(run: AnalysisRun):
    run.status = 'processing'
    run.save(update_fields=['status'])
    geom = load_aoi_shape()
    ndvi_baseline = get_baseline_ndvi_for_run(run)
    outputs = compute_run_outputs(
        geom=geom,
        start_date=run.start_date,
        end_date=run.end_date,
        ndvi_baseline=ndvi_baseline,
    )
    return save_run_outputs(run, outputs)


def seed_historical_runs():
    processed = []
    for spec in historical_run_specs():
        run = get_or_create_run(spec)
        print(f"Processing: {run.record_key}")
        processed.append(process_run(run))
    return processed


def seed_future_runs(
    until_date: date,
    *,
    completed_only: bool = True,
    skip_ready: bool = True,
):
    processed = []

    specs = (
        completed_future_run_specs(until_date)
        if completed_only
        else future_run_specs(until_date)
    )

    for spec in specs:
        existing = AnalysisRecord.objects.filter(
            analysis_type=RUN_SUMMARY_TYPE,
            record_key=spec["record_key"],
        ).first()

        if skip_ready and existing and existing.status == "ready":
            continue

        run = get_or_create_run(spec)
        processed.append(process_run(run))

    return processed
    

def build_layer_urls(run, layer_name: str, request=None):
    image_path = reverse('api_v1_layer_image', kwargs={'run_id': run.id, 'layer_name': layer_name})
    raster_path = reverse('api_v1_layer_raster', kwargs={'run_id': run.id, 'layer_name': layer_name})
    metadata_path = reverse('api_v1_layer_detail', kwargs={'run_id': run.id, 'layer_name': layer_name})
    if request is not None:
        return {
            'image_url': request.build_absolute_uri(image_path),
            'raster_url': request.build_absolute_uri(raster_path),
            'detail_url': request.build_absolute_uri(metadata_path),
        }
    return {
        'image_url': image_path,
        'raster_url': raster_path,
        'detail_url': metadata_path,
    }


def serialize_layer(layer: AnalysisLayer, request=None):
    urls = build_layer_urls(layer.run, layer.layer_name, request=request)
    return {
        'layer_name': layer.layer_name,
        'bounds': layer_extent_bounds(layer.id),
        'band_count': layer.band_count,
        'srid': layer.srid,
        'width': layer.width,
        'height': layer.height,
        'nodata': layer.nodata,
        'min_value': layer.min_value,
        'max_value': layer.max_value,
        'stats': layer.stats or {},
        'style_config': layer.style_config or {},
        **urls,
    }


def serialize_run_list_item(run: AnalysisRun, request=None):
    detail_path = reverse('api_v1_run_detail', kwargs={'run_id': run.id})
    detail_url = request.build_absolute_uri(detail_path) if request is not None else detail_path
    return {
        'run_id': str(run.id),
        'record_key': run.record_key,
        'mode': run.mode,
        'year': run.year,
        'season': run.season,
        'window_index': run.window_index,
        'window_label': run.window_label,
        'start_date': run.start_date.isoformat(),
        'end_date': run.end_date.isoformat(),
        'status': run.status,
        'source_sensor': run.source_sensor,
        'fallback_used': run.fallback_used,
        'confidence': run.confidence,
        'mean_cloud_cover': run.mean_cloud_cover,
        'mean_ndvi': run.mean_ndvi,
        'mean_ndmi': run.mean_ndmi,
        'mean_awei': run.mean_awei,
        'detail_url': detail_url,
    }


def get_layer_or_404(run_id, layer_name: str):
    return get_object_or_404(AnalysisLayer.objects.select_related('run'), run_id=run_id, layer_name=layer_name)

def build_dashboard_config():
    aoi = load_aoi_feature()
    historical = {}
    for run in AnalysisRun.objects.filter(mode='historical').order_by('year', 'start_date'):
        historical.setdefault(str(run.year), []).append(
            {
                'season': run.season,
                'run_id': str(run.id),
                'status': run.status,
                'source_sensor': run.source_sensor,
                'fallback_used': run.fallback_used,
            }
        )

    future_runs = [
        {
            'run_id': str(run.id),
            'year': run.year,
            'label': run.window_label or run.record_key,
            'record_key': run.record_key,
            'status': run.status,
            'source_sensor': run.source_sensor,
        }
        for run in AnalysisRun.objects.filter(mode='future').order_by('start_date')
    ]

    dem_path = Path(settings.LOCAL_DEM_PATH)
    return {
        'aoi': {'type': 'FeatureCollection', 'features': [aoi]},
        'seasons': list(SEASONS.keys()),
        'theme_options': THEME_LABELS,
        'theme_guides': LAYER_GUIDES,
        'layer_by_theme': LAYER_BY_THEME,
        'historical_years': sorted(historical.keys()),
        'historical_runs': historical,
        'future_runs': future_runs,
        'default_historical_year': str(settings.HISTORICAL_END_YEAR),
        'default_historical_season': 'Post-Monsoon',
        'future_start_date': settings.FUTURE_START_DATE.isoformat(),
        'has_local_dem': dem_path.exists(),
        'local_dem_path': str(dem_path),
        'api_root': '/api/v1',
    }


def serialize_run(run: AnalysisRun, request=None):
    layers = {
        layer.layer_name: serialize_layer(layer, request=request)
        for layer in run.layers.all()
    }
    return {
        'run_id': str(run.id),
        'record_key': run.record_key,
        'mode': run.mode,
        'year': run.year,
        'season': run.season,
        'window_label': run.window_label,
        'window_index': run.window_index,
        'start_date': run.start_date.isoformat(),
        'end_date': run.end_date.isoformat(),
        'status': run.status,
        'source_sensor': run.source_sensor,
        'fallback_used': run.fallback_used,
        'confidence': run.confidence,
        'mean_cloud_cover': run.mean_cloud_cover,
        'mean_ndvi': run.mean_ndvi,
        'mean_ndmi': run.mean_ndmi,
        'mean_awei': run.mean_awei,
        'summary_cards': run.summary_cards,
        'stats_cache': run.stats_cache,
        'layers': layers,
        'available_themes': [theme for theme, layer_name in LAYER_BY_THEME.items() if layer_name in layers],
        'has_optical': 'ndvi' in layers,
        'has_radar': 'radar' in layers,
    }


def get_run_for_selection(mode: str, year: Optional[int] = None, season: Optional[str] = None, run_id: Optional[str] = None):
    qs = AnalysisRun.objects.prefetch_related('layers')
    if run_id:
        return get_object_or_404(qs, id=run_id)
    if mode == 'historical':
        return get_object_or_404(qs, mode='historical', year=year, season=season)
    return get_object_or_404(qs, id=run_id)


def _safe_float(value):
    return None if value is None else float(value)


def _flatten_layer_values(layer: AnalysisLayer):
    arr, _, _, nodata = load_layer_array(layer.id)
    single = arr[0].astype('float32') if arr.ndim == 3 else arr.astype('float32')
    if nodata is not None:
        single = np.where(np.isclose(single, nodata), np.nan, single)
    values = single[np.isfinite(single)]
    return values


def _style_range(layer_name: str, values: np.ndarray):
    style = STYLE_CONFIGS.get(layer_name, {})
    vmin = style.get('min')
    vmax = style.get('max')
    if isinstance(vmin, list) or isinstance(vmax, list):
        vmin = None
        vmax = None
    if vmin is None or vmax is None:
        if values.size:
            vmin = float(np.nanmin(values))
            vmax = float(np.nanmax(values))
        else:
            vmin, vmax = 0.0, 1.0
    if abs(vmax - vmin) < 1e-9:
        vmax = vmin + 1.0
    return float(vmin), float(vmax)


def _build_histogram(layer_name: str, values: np.ndarray, bins: int = 12):
    if values.size == 0:
        return {'labels': [], 'values': [], 'title': 'Distribution'}
    vmin, vmax = _style_range(layer_name, values)
    hist, edges = np.histogram(values, bins=bins, range=(vmin, vmax))
    labels = [f'{edges[i]:.2f} - {edges[i + 1]:.2f}' for i in range(len(edges) - 1)]
    return {
        'labels': labels,
        'values': hist.astype(int).tolist(),
        'title': f'{THEME_BY_LAYER.get(layer_name, layer_name)} distribution',
    }


def _build_class_breakdown(layer_name: str, values: np.ndarray):
    if values.size == 0:
        return {'labels': [], 'values': [], 'counts': [], 'title': 'Class share'}
    specs = CLASS_SPECS.get(layer_name)
    if specs is None:
        vmin, vmax = _style_range(layer_name, values)
        edges = np.linspace(vmin, vmax, 6)
        specs = [(f'Class {i + 1}', float(edges[i]), float(edges[i + 1])) for i in range(len(edges) - 1)]
        specs[-1] = (specs[-1][0], specs[-1][1], 999999.0)
    labels, counts = [], []
    for idx, (label, lower, upper) in enumerate(specs):
        if idx == len(specs) - 1:
            mask = (values >= lower) & (values <= upper)
        else:
            mask = (values >= lower) & (values < upper)
        labels.append(label)
        counts.append(int(np.sum(mask)))
    total = max(sum(counts), 1)
    percentages = [round((count / total) * 100.0, 2) for count in counts]
    return {
        'labels': labels,
        'values': percentages,
        'counts': counts,
        'title': f'{THEME_BY_LAYER.get(layer_name, layer_name)} class share',
    }


def _build_theme_comparison(run: AnalysisRun):
    stats_cache = run.stats_cache or {}
    labels = []
    values = []
    raw_values = []
    themes = []
    for theme, layer_name in LAYER_BY_THEME.items():
        stat = stats_cache.get(layer_name, {})
        mean_val = stat.get('mean')
        if mean_val is None:
            continue
        style = STYLE_CONFIGS.get(layer_name, {})
        if style.get('mode') == 'single' and style.get('min') is not None and style.get('max') is not None:
            span = max(float(style['max']) - float(style['min']), 1e-9)
            normalized = (float(mean_val) - float(style['min'])) / span
            normalized = max(0.0, min(1.0, normalized))
        else:
            normalized = float(mean_val)
        labels.append(theme)
        values.append(round(normalized, 4))
        raw_values.append(round(float(mean_val), 4))
        themes.append(theme)
    return {
        'labels': labels,
        'values': values,
        'raw_values': raw_values,
        'themes': themes,
        'title': 'Normalized mean score by theme',
    }


def build_trend_payload(mode: str = 'historical', season: str = 'Monsoon', layer_name: str = 'ndvi'):
    if mode == 'historical':
        runs = AnalysisRun.objects.filter(mode='historical', season=season, status='ready').order_by('year')
        labels = []
        values = []
        selectors = []
        for run in runs:
            mean_val = (run.stats_cache or {}).get(layer_name, {}).get('mean')
            if mean_val is None:
                continue
            labels.append(str(run.year))
            values.append(float(mean_val))
            selectors.append({'run_id': str(run.id), 'year': run.year, 'season': run.season})
        title = f'{THEME_BY_LAYER.get(layer_name, layer_name)} trend across {season}'
    else:
        runs = AnalysisRun.objects.filter(mode='future', status='ready').order_by('start_date')
        labels = []
        values = []
        selectors = []
        for run in runs:
            mean_val = (run.stats_cache or {}).get(layer_name, {}).get('mean')
            if mean_val is None:
                continue
            labels.append(run.window_label or run.start_date.isoformat())
            values.append(float(mean_val))
            selectors.append({'run_id': str(run.id)})
        title = f'{THEME_BY_LAYER.get(layer_name, layer_name)} trend across future windows'
    return {
        'mode': mode,
        'season': season,
        'layer_name': layer_name,
        'title': title,
        'series': [{'label': label, 'value': value, 'selector': selector} for label, value, selector in zip(labels, values, selectors)],
    }


def build_chart_payload(run: AnalysisRun, layer_name: str):
    layer_map = {layer.layer_name: layer for layer in run.layers.all()}
    target_layer = layer_map.get(layer_name)
    if target_layer is None:
        available = sorted(layer_map.keys())
        fallback_name = available[0] if available else layer_name
        target_layer = layer_map.get(fallback_name)
        layer_name = fallback_name

    values = _flatten_layer_values(target_layer) if target_layer is not None else np.array([], dtype='float32')
    stats = (run.stats_cache or {}).get(layer_name, {})
    trend = build_trend_payload(
        mode=run.mode,
        season=run.season or 'Monsoon',
        layer_name=layer_name,
    )
    return {
        'run_id': str(run.id),
        'layer_name': layer_name,
        'layer_label': THEME_BY_LAYER.get(layer_name, layer_name),
        'histogram': _build_histogram(layer_name, values),
        'class_breakdown': _build_class_breakdown(layer_name, values),
        'comparison': _build_theme_comparison(run),
        'trend': trend,
        'stats': {
            'labels': ['Mean', 'Median', 'Q1', 'Q3', 'Min', 'Max', 'Std'],
            'values': [
                _safe_float(stats.get('mean')),
                _safe_float(stats.get('median')),
                _safe_float(stats.get('q25')),
                _safe_float(stats.get('q75')),
                _safe_float(stats.get('min')),
                _safe_float(stats.get('max')),
                _safe_float(stats.get('std')),
            ],
            'title': f'{THEME_BY_LAYER.get(layer_name, layer_name)} summary statistics',
        },
    }


def inspect_run_point(run: AnalysisRun, lon: float, lat: float):
    layer_map = {layer.layer_name: layer for layer in run.layers.all()}

    def value(name, band=1):
        layer = layer_map.get(name)
        if not layer:
            return None
        return sample_layer_value(layer.id, lon, lat, band=band)

    ndvi = value('ndvi')
    ndmi = value('ndmi')
    ndvi_anomaly = value('ndvi_anomaly')
    waterlite = value('waterlite')
    slope = value('slope')
    coconut = value('coconut')
    pepper = value('pepper')
    mudcottage = value('mudcottage')
    sandalwood = value('sandalwood')
    waterharvesting = value('waterharvesting')
    elevation = value('dem')

    if ndvi is None:
        return {
            'message': 'No optical data at this point. Use radar and terrain layers.',
            'metrics': {},
            'best_use': None,
            'risk': 'Clouded or unavailable',
            'advice': 'Inspect radar/terrain layers for this location.',
        }

    scores = {
        'Coconut': coconut or 0,
        'Pepper': pepper or 0,
        'Eco-Stay': mudcottage or 0,
        'Sandalwood': sandalwood or 0,
        'Check-Dam': waterharvesting or 0,
    }
    best_use = max(scores, key=scores.get)
    if scores[best_use] <= 0.4:
        best_use = 'Conservation Zone'

    risk = 'Low Risk'
    advice = 'Standard zoning.'
    if slope is not None and slope > 25:
        risk = 'Erosion (Steep)'
        advice = 'Avoid building. Prefer soil-binders and slope stabilization.'
    elif waterlite is not None and waterlite > 0.65:
        risk = 'Waterlogging'
        advice = 'Avoid cottages and plan drainage.'
    elif ndvi_anomaly is not None and ndvi_anomaly < -0.10:
        risk = 'Vegetation Stress'
        advice = 'Inspect for pests, drought, or nutrient stress.'

    metrics = {
        'elevation': elevation,
        'slope': slope,
        'ndvi': ndvi,
        'ndmi': ndmi,
        'ndvi_anomaly': ndvi_anomaly,
        'waterlite': waterlite,
        'coconut': coconut,
        'pepper': pepper,
        'mudcottage': mudcottage,
        'sandalwood': sandalwood,
        'waterharvesting': waterharvesting,
    }
    return {
        'message': 'Point diagnostics ready.',
        'metrics': metrics,
        'best_use': best_use,
        'risk': risk,
        'advice': advice,
    }



def get_layer_gtiff_bytes(run_id, layer_name: str):
    layer = get_layer_or_404(run_id, layer_name)
    return layer, read_layer_gtiff_bytes(layer.id)


def build_selection_trend_payload(season: str):
    rows = (
        AnalysisRecord.objects.filter(
            analysis_type="summary",
            mode="historical",
            season=season,
            status="ready",
        )
        .exclude(year__isnull=True)
        .order_by("year")
    )

    ndvi = []
    ndmi = []
    awei = []

    for row in rows:
        if row.mean_ndvi is not None:
            ndvi.append({"year": row.year, "value": row.mean_ndvi})
        if row.mean_ndmi is not None:
            ndmi.append({"year": row.year, "value": row.mean_ndmi})
        if row.mean_awei is not None:
            awei.append({"year": row.year, "value": row.mean_awei})

    return {
        "ndvi": ndvi,
        "ndmi": ndmi,
        "awei": awei,
    }