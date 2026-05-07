from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from statistics import mean
from typing import Dict, List, Optional

import numpy as np
import planetary_computer
import rasterio
from django.conf import settings
from pyproj import CRS, Transformer
from pystac_client import Client
from rasterio.enums import Resampling
from rasterio.mask import mask
from rasterio.transform import Affine
from rasterio.warp import reproject
from shapely.geometry import mapping, shape
from shapely.ops import transform as shapely_transform


@dataclass
class RasterBundle:
    arrays: Dict[str, np.ndarray]
    transform: Affine
    crs: CRS
    nodata: float
    valid_fraction: float
    selected_item_ids: List[str]
    mean_cloud_cover: Optional[float] = None


S2_BANDS = ['B02', 'B03', 'B04', 'B08', 'B11', 'B12', 'SCL']
S1_VV_KEYS = ['vv', 'VV']
S1_VH_KEYS = ['vh', 'VH']
DEM_ASSET_KEYS = ['data', 'dem']


def get_catalog():
    return Client.open(settings.PLANETARY_COMPUTER_STAC)


def load_aoi_feature():
    with open(settings.AOI_GEOJSON_PATH, 'r', encoding='utf-8') as fh:
        geojson = json.load(fh)
    return geojson['features'][0]


def _force_2d(geom):
    return shapely_transform(lambda x, y, z=None: (x, y), geom)


def load_aoi_shape():
    return _force_2d(shape(load_aoi_feature()['geometry']))


def _safe_crs(crs_like):
    if crs_like in (None, '', ':'):
        return None
    try:
        return CRS.from_user_input(crs_like)
    except Exception:
        return None


def _geom_to_dataset_crs(geom, dataset_crs):
    src_crs = CRS.from_epsg(4326)
    dst_crs = _safe_crs(dataset_crs)
    if dst_crs is None:
        raise ValueError('Raster asset has no valid CRS')
    if src_crs == dst_crs:
        return geom
    transformer = Transformer.from_crs(src_crs, dst_crs, always_xy=True)
    return shapely_transform(transformer.transform, geom)


def bbox_from_geom(geom):
    minx, miny, maxx, maxy = geom.bounds
    return [minx, miny, maxx, maxy]


def sign_item(item):
    return planetary_computer.sign(item)


def normalize(arr, min_val, max_val):
    out = (arr - min_val) / max(max_val - min_val, 1e-9)
    return np.clip(out, 0, 1)


def _safe_div(numer, denom):
    denom = np.where(np.abs(denom) < 1e-9, np.nan, denom)
    return numer / denom


def compute_indices(composite):
    ndvi = _safe_div(composite['B08'] - composite['B04'], composite['B08'] + composite['B04'])
    ndmi = _safe_div(composite['B08'] - composite['B11'], composite['B08'] + composite['B11'])
    awei = 4 * (composite['B03'] - composite['B11']) - (0.25 * composite['B08'] + 2.75 * composite['B12'])
    return {'ndvi': ndvi.astype('float32'), 'ndmi': ndmi.astype('float32'), 'awei': awei.astype('float32')}


def build_waterlite(dem, slope, ndmi, awei):
    rel_elev = normalize(dem, 700, 950)
    lowland = 1.0 - rel_elev
    slope_inv = 1.0 - normalize(slope, 0, 30)
    moist_norm = normalize(ndmi, -0.2, 0.4)
    water_norm = normalize(awei, -2, 2)
    return (
        lowland * 0.35
        + slope_inv * 0.25
        + moist_norm * 0.25
        + water_norm * 0.15
    ).astype('float32')


def build_suitability_layers(ndvi, waterlite, slope):
    slope_flat = 1.0 - np.clip(slope / 15.0, 0, 1)
    slope_mod = 1.0 - np.clip(np.abs(slope - 15.0) / 10.0, 0, 1)
    drainage_good = np.clip(1.0 - waterlite, 0, 1)
    moisture_high = np.clip(waterlite, 0, 1)
    veg_dense = normalize(ndvi, 0.3, 0.8)
    steep_penalty = (slope < 25).astype('float32')

    coconut = (slope_flat * 0.40 + moisture_high * 0.40 + veg_dense * 0.20) * steep_penalty
    pepper = (slope_mod * 0.40 + drainage_good * 0.30 + veg_dense * 0.30) * steep_penalty
    mudcottage = (drainage_good * 0.60 + slope_flat * 0.40) * steep_penalty
    sandalwood = (drainage_good * 0.40 + slope_mod * 0.40 + veg_dense * 0.20) * steep_penalty
    waterharvesting = (moisture_high * 0.60 + slope_flat * 0.40) * steep_penalty

    return {
        'coconut': coconut.astype('float32'),
        'pepper': pepper.astype('float32'),
        'mudcottage': mudcottage.astype('float32'),
        'sandalwood': sandalwood.astype('float32'),
        'waterharvesting': waterharvesting.astype('float32'),
    }


def calculate_slope_deg(dem, transform):
    xres = abs(transform.a) or 10.0
    yres = abs(transform.e) or 10.0
    gy, gx = np.gradient(dem.astype('float32'), yres, xres)
    return np.degrees(np.arctan(np.sqrt(gx * gx + gy * gy))).astype('float32')


def _crop_asset(asset_href, geom, all_touched=True):
    with rasterio.open(asset_href) as src:
        geom_in_src = _geom_to_dataset_crs(geom, src.crs)
        out, transform = mask(
            src,
            [mapping(geom_in_src)],
            crop=True,
            filled=True,
            all_touched=all_touched,
        )
        return out[0], transform, src.crs, src.nodata


def _reproject_array(src_array, src_transform, src_crs, target_shape, target_transform, target_crs, resampling=Resampling.nearest):
    dst = np.full(target_shape, np.nan, dtype='float32')
    reproject(
        source=src_array.astype('float32'),
        destination=dst,
        src_transform=src_transform,
        src_crs=src_crs,
        src_nodata=np.nan,
        dst_transform=target_transform,
        dst_crs=target_crs,
        dst_nodata=np.nan,
        resampling=resampling,
    )
    return dst


def _read_asset_on_grid(
    asset_href,
    geom,
    target_transform=None,
    target_crs=None,
    target_shape=None,
    resampling=Resampling.nearest,
    all_touched=True,
):
    arr, transform, crs, nodata = _crop_asset(asset_href, geom, all_touched=all_touched)
    arr = arr.astype("float32")
    if nodata is not None:
        arr = np.where(np.isclose(arr, nodata), np.nan, arr)
    if target_transform is None:
        return arr, transform, _safe_crs(crs), arr.shape
    if str(crs) == str(target_crs) and arr.shape == target_shape and transform == target_transform:
        return arr, transform, _safe_crs(crs), arr.shape
    warped = _reproject_array(
        arr,
        transform,
        crs,
        target_shape,
        target_transform,
        target_crs,
        resampling=resampling,
    )
    return warped, target_transform, target_crs, target_shape
  

def _signed_asset_href(item, keys):
    signed = sign_item(item)
    for key in keys:
        if key in signed.assets:
            return signed.assets[key].href
    raise KeyError(f'None of the requested asset keys were found: {keys}')


def _date_part(value):
    return value.isoformat() if hasattr(value, 'isoformat') else str(value)


def _chunk_date_ranges(start_date, end_date, days=31):
    current = start_date
    while current <= end_date:
        chunk_end = min(current + timedelta(days=days - 1), end_date)
        yield current, chunk_end
        current = chunk_end + timedelta(days=1)


def _item_sort_key(item):
    dt = getattr(item, 'datetime', None)
    return dt.isoformat() if dt else item.id

def search_items(collections, geom, start_date, end_date, query=None, max_items=None):
    catalog = get_catalog()
    query = query or {}
    target_max = max_items or settings.MAX_ITEMS
    per_chunk_limit = min(target_max, 30)

    merged = {}

    for chunk_start, chunk_end in _chunk_date_ranges(start_date, end_date, days=31):
        inclusive_end = chunk_end + timedelta(days=1)
        try:
            search = catalog.search(
                collections=collections,
                intersects=mapping(geom),
                datetime=f'{_date_part(chunk_start)}/{_date_part(inclusive_end)}',
                query=query,
                limit=per_chunk_limit,
            )
            for item in search.items():
                merged[item.id] = item
        except Exception:
            continue

    items = list(merged.values())
    items.sort(key=_item_sort_key)

    return items[:target_max]

def _s2_processing_baseline(item) -> Optional[float]:
    value = item.properties.get('s2:processing_baseline')
    if value is None:
        return None
    try:
        return float(str(value))
    except Exception:
        return None


def _needs_s2_harmonization(item) -> bool:
    baseline = _s2_processing_baseline(item)
    if baseline is not None:
        return baseline >= 4.0

    dt = getattr(item, 'datetime', None)
    return bool(dt and dt.date().isoformat() >= '2022-01-25')


def _s2_clear_mask(arrays) -> np.ndarray:
    scl = arrays['SCL']
    scl_valid = np.isfinite(scl)
    scl_int = np.where(scl_valid, scl, -9999).astype('int16')
    return scl_valid & ~np.isin(scl_int, [0, 1, 3, 8, 9, 10, 11])


def build_s2_bundle(geom, start_date, end_date) -> Optional[RasterBundle]:
    items = search_items(
        [settings.SENTINEL2_COLLECTION],
        geom,
        start_date,
        end_date,
        query={'eo:cloud_cover': {'lte': settings.SENTINEL2_CLOUD_THRESHOLD}},
        max_items=settings.MAX_ITEMS,
    )
    if not items:
        return None

    stacks = {band: [] for band in S2_BANDS[:-1]}
    target_transform = None
    target_crs = None
    target_shape = None
    cloud_values = []
    selected_ids = []

    for item in items:
        signed = sign_item(item)
        arrays = {}
        try:
            for band in S2_BANDS:
                if band not in signed.assets:
                    arrays = {}
                    break
                href = signed.assets[band].href
                if target_transform is None:
                    arr, target_transform, target_crs, target_shape = _read_asset_on_grid(href, geom)
                else:
                    arr, _, _, _ = _read_asset_on_grid(
                        href,
                        geom,
                        target_transform=target_transform,
                        target_crs=target_crs,
                        target_shape=target_shape,
                        resampling=Resampling.nearest,
                    )
                arrays[band] = arr
        except Exception:
            arrays = {}
        if not arrays:
            continue

        
        clear_mask = _s2_clear_mask(arrays)

        for band in S2_BANDS[:-1]:
            raw = arrays[band].astype('float32')

            # Match GEE harmonized behavior for 2022+ scenes
            if _needs_s2_harmonization(item):
                raw = np.clip(raw - 1000.0, 0, None)

            scaled = raw / 10000.0
            scaled = np.where(clear_mask, scaled, np.nan)
            stacks[band].append(scaled.astype('float32'))

        selected_ids.append(item.id)
        cc = item.properties.get('eo:cloud_cover')
        if cc is not None:
            cloud_values.append(float(cc))

    if not selected_ids or not all(stacks.values()):
        return None

    composite = {}
    for band, band_arrays in stacks.items():
        band_stack = np.stack(band_arrays, axis=0)
        composite[band] = np.nanmedian(band_stack, axis=0).astype('float32')

    ndvi = _safe_div(composite['B08'] - composite['B04'], composite['B08'] + composite['B04'])
    valid_fraction = float(np.mean(np.isfinite(ndvi)))
    return RasterBundle(
        arrays=composite,
        transform=target_transform,
        crs=target_crs,
        nodata=settings.RASTER_NODATA,
        valid_fraction=valid_fraction,
        selected_item_ids=selected_ids,
        mean_cloud_cover=mean(cloud_values) if cloud_values else None,
    )


def build_s1_bundle(geom, start_date, end_date) -> Optional[RasterBundle]:
    items = search_items(
        [settings.SENTINEL1_COLLECTION],
        geom,
        start_date,
        end_date,
        query={'sar:instrument_mode': {'eq': 'IW'}},
        max_items=max(settings.MAX_ITEMS, 120),
    )
    if not items:
        return None

    vv_stack = []
    vh_stack = []
    target_transform = None
    target_crs = None
    target_shape = None
    selected_ids = []

    for item in items:
        signed = sign_item(item)
        vv_key = next((k for k in S1_VV_KEYS if k in signed.assets), None)
        vh_key = next((k for k in S1_VH_KEYS if k in signed.assets), None)
        if not vv_key or not vh_key:
            continue
        vv_href = signed.assets[vv_key].href
        vh_href = signed.assets[vh_key].href
        try:
            if target_transform is None:
                vv, target_transform, target_crs, target_shape = _read_asset_on_grid(vv_href, geom)
            else:
                vv, _, _, _ = _read_asset_on_grid(vv_href, geom, target_transform, target_crs, target_shape)
            vh, _, _, _ = _read_asset_on_grid(vh_href, geom, target_transform, target_crs, target_shape)
        except Exception:
            continue
        vv = 10 * np.log10(np.clip(vv, 1e-6, None))
        vh = 10 * np.log10(np.clip(vh, 1e-6, None))
        vv_stack.append(vv.astype('float32'))
        vh_stack.append(vh.astype('float32'))
        selected_ids.append(item.id)

    if not selected_ids or not vv_stack or not vh_stack:
        return None

    vv_med = np.nanmedian(np.stack(vv_stack, axis=0), axis=0).astype('float32')
    vh_med = np.nanmedian(np.stack(vh_stack, axis=0), axis=0).astype('float32')
    ratio = (vv_med - vh_med).astype('float32')
    valid_fraction = float(np.mean(np.isfinite(vv_med) & np.isfinite(vh_med)))

    return RasterBundle(
        arrays={'vv': vv_med, 'vh': vh_med, 'ratio': ratio},
        transform=target_transform,
        crs=target_crs,
        nodata=settings.RASTER_NODATA,
        valid_fraction=valid_fraction,
        selected_item_ids=selected_ids,
    )


def _build_local_dem_array(geom, target_transform, target_crs, target_shape, dem_path: Path):
    arr, transform, crs, nodata = _crop_asset(str(dem_path), geom, all_touched=True)
    arr = arr.astype('float32')
    if nodata is not None:
        arr = np.where(np.isclose(arr, nodata), np.nan, arr)
    if target_transform is None:
        return arr
    if str(crs) == str(target_crs) and arr.shape == target_shape and transform == target_transform:
        return arr
    return _reproject_array(arr, transform, crs, target_shape, target_transform, target_crs, resampling=Resampling.nearest)


def build_dem_array(geom, target_transform, target_crs, target_shape):
    dem_path = Path(settings.LOCAL_DEM_PATH)
    if dem_path.exists():
        return _build_local_dem_array(geom, target_transform, target_crs, target_shape, dem_path)

    if not settings.DEM_SOURCE_FALLBACK_TO_STAC:
        raise RuntimeError(f'Local DEM not found at {dem_path}')

    items = search_items(
        [settings.DEM_COLLECTION],
        geom,
        start_date='2010-01-01',
        end_date='2030-12-31',
        max_items=12,
    )
    if not items:
        raise RuntimeError('No DEM tiles found in Planetary Computer for the AOI.')

    dem_arrays = []
    for item in items:
        signed = sign_item(item)
        key = next((k for k in DEM_ASSET_KEYS if k in signed.assets), None)
        if not key:
            continue
        arr, _, _, _ = _read_asset_on_grid(
            signed.assets[key].href,
            geom,
            target_transform=target_transform,
            target_crs=target_crs,
            target_shape=target_shape,
            resampling=Resampling.nearest,
        )
        dem_arrays.append(arr.astype('float32'))

    if not dem_arrays:
        raise RuntimeError('DEM asset keys were not found on the DEM items.')

    dem = np.nanmedian(np.stack(dem_arrays, axis=0), axis=0).astype('float32')
    return dem


def classify_confidence(valid_fraction):
    if valid_fraction < 0.40:
        return 'Low (High Clouds)'
    if valid_fraction < 0.70:
        return 'Medium'
    return 'High'


def _align_baseline_to_grid(ndvi_baseline, target_shape, target_transform, target_crs):
    if ndvi_baseline is None:
        return None

    if isinstance(ndvi_baseline, np.ndarray):
        if ndvi_baseline.shape == target_shape:
            return ndvi_baseline.astype('float32')
        return None

    src = ndvi_baseline.get('array')
    src_transform = ndvi_baseline.get('transform')
    src_crs = ndvi_baseline.get('crs')

    if src is None or src_transform is None or src_crs is None:
        return None

    dst = np.full(target_shape, np.nan, dtype='float32')
    reproject(
        source=src.astype('float32'),
        destination=dst,
        src_transform=src_transform,
        src_crs=src_crs,
        src_nodata=np.nan,
        dst_transform=target_transform,
        dst_crs=target_crs,
        dst_nodata=np.nan,
        resampling=Resampling.nearest,
    )
    return dst

def compute_run_outputs(geom, start_date, end_date, ndvi_baseline=None):
    s2 = build_s2_bundle(geom, start_date, end_date)
    s1 = build_s1_bundle(geom, start_date, end_date)

    source_sensor = 'UNAVAILABLE'
    fallback_used = False
    arrays = {}
    transform = None
    crs = None
    nodata = settings.RASTER_NODATA
    valid_fraction = 0.0
    selected_item_ids = []
    mean_cloud_cover = None

    if s2 is not None:
        source_sensor = 'S2_WITH_S1_SUPPORT' if s1 is not None else 'S2'
        arrays.update(s2.arrays)
        transform = s2.transform
        crs = s2.crs
        valid_fraction = s2.valid_fraction
        selected_item_ids.extend(s2.selected_item_ids)
        mean_cloud_cover = s2.mean_cloud_cover
    elif s1 is not None:
        source_sensor = 'S1_FALLBACK'
        fallback_used = True
        transform = s1.transform
        crs = s1.crs
        valid_fraction = s1.valid_fraction
        selected_item_ids.extend(s1.selected_item_ids)

    if transform is None or crs is None:
        return {
            'status': 'empty',
            'source_sensor': 'UNAVAILABLE',
            'fallback_used': False,
            'layers': {},
            'summary_cards': {},
            'stats_cache': {},
            'valid_pixel_fraction': 0.0,
            'confidence': 'Low',
            'selected_item_ids': [],
            'mean_cloud_cover': None,
        }

    base_shape = next(iter(arrays.values())).shape if arrays else next(iter(s1.arrays.values())).shape
    dem = build_dem_array(geom, transform, crs, base_shape)
    slope = calculate_slope_deg(dem, transform)

    layer_arrays = {
        'dem': dem.astype('float32'),
        'slope': slope.astype('float32'),
    }

    if s2 is not None:
        indices = compute_indices(s2.arrays)
        ndvi = indices['ndvi']
        ndmi = indices['ndmi']
        awei = indices['awei']
        aligned_baseline = _align_baseline_to_grid(ndvi_baseline, ndvi.shape, transform, crs)
        ndvi_anomaly = (ndvi - aligned_baseline) if aligned_baseline is not None else np.zeros_like(ndvi, dtype='float32')
        waterlite = build_waterlite(dem, slope, ndmi, awei)
        suitability = build_suitability_layers(ndvi, waterlite, slope)

        rgb = np.stack([s2.arrays['B04'], s2.arrays['B03'], s2.arrays['B02']], axis=0).astype('float32')
        layer_arrays.update(
            {
                'rgb': rgb,
                'ndvi': ndvi.astype('float32'),
                'ndmi': ndmi.astype('float32'),
                'awei': awei.astype('float32'),
                'ndvi_anomaly': ndvi_anomaly.astype('float32'),
                'waterlite': waterlite.astype('float32'),
                **suitability,
            }
        )

    if s1 is not None:
        radar = np.stack([s1.arrays['vv'], s1.arrays['vh'], s1.arrays['ratio']], axis=0).astype('float32')
        layer_arrays['radar'] = radar

    stats_cache = {}
    summary_cards = {}

    if 'ndvi' in layer_arrays:
        ndvi = layer_arrays['ndvi']
        ndmi = layer_arrays['ndmi']
        waterlite = layer_arrays['waterlite']
        coconut = layer_arrays['coconut']
        pepper = layer_arrays['pepper']
        mudcottage = layer_arrays['mudcottage']
        sandalwood = layer_arrays['sandalwood']
        waterharvesting = layer_arrays['waterharvesting']

        max_suit = np.nanmax(np.stack([coconut, pepper, mudcottage, sandalwood, waterharvesting], axis=0), axis=0)
        viable = max_suit > 0.60
        areas = {
            'Coconut Planting': float(np.mean((coconut == max_suit) & viable)),
            'Pepper Vines': float(np.mean((pepper == max_suit) & viable)),
            'Eco-Stay': float(np.mean((mudcottage == max_suit) & viable)),
            'Silviculture': float(np.mean((sandalwood == max_suit) & viable)),
            'Rainwater Harvesting': float(np.mean((waterharvesting == max_suit) & viable)),
        }
        top_zoning = max(areas, key=areas.get) if any(v > 0 for v in areas.values()) else 'Awaiting Selection'
        summary_cards = {
            'vegetation': 'Vigorous' if float(np.nanmean(ndvi)) >= 0.6 else ('Moderate' if float(np.nanmean(ndvi)) >= 0.4 else 'Stressed'),
            'moisture': 'Wet' if float(np.nanmean(ndmi)) >= 0.2 else ('Balanced' if float(np.nanmean(ndmi)) >= 0 else 'Dry'),
            'top_zoning': top_zoning,
            'primary_risk': 'Steepness' if float(np.nanmean(slope)) > 15 else ('Waterlogging' if float(np.nanmean(waterlite)) > 0.45 else 'Vegetation Stress'),
        }
    else:
        summary_cards = {
            'vegetation': 'Radar only',
            'moisture': 'Radar only',
            'top_zoning': 'Awaiting Optical Data',
            'primary_risk': 'Cloud cover too high',
        }

    for name, arr in layer_arrays.items():
        single = arr[0] if arr.ndim == 3 else arr
        valid = np.isfinite(single)
        if not np.any(valid):
            stats_cache[name] = {'mean': None, 'min': None, 'max': None, 'std': None, 'median': None, 'q25': None, 'q75': None, 'valid_pixels': 0}
            continue
        stats_cache[name] = {
            'mean': float(np.nanmean(single)),
            'min': float(np.nanmin(single)),
            'max': float(np.nanmax(single)),
            'std': float(np.nanstd(single)),
            'median': float(np.nanmedian(single)),
            'q25': float(np.nanpercentile(single, 25)),
            'q75': float(np.nanpercentile(single, 75)),
            'valid_pixels': int(np.sum(valid)),
        }

    return {
        'status': 'ready',
        'source_sensor': source_sensor,
        'fallback_used': fallback_used,
        'layers': layer_arrays,
        'transform': transform,
        'crs': crs,
        'nodata': nodata,
        'summary_cards': summary_cards,
        'stats_cache': stats_cache,
        'valid_pixel_fraction': valid_fraction,
        'confidence': classify_confidence(valid_fraction),
        'selected_item_ids': selected_item_ids,
        'mean_cloud_cover': mean_cloud_cover,
    }
