import io
from typing import Tuple

import numpy as np
import rasterio
from PIL import Image
from django.contrib.gis.geos import Polygon
from django.db import connection
from rasterio.io import MemoryFile
from rasterio.features import geometry_mask
from rasterio.transform import Affine
from rasterio.warp import transform_geom
from .processing import load_aoi_feature




def array_to_gtiff_bytes(array: np.ndarray, transform, crs, nodata=None, dtype="float32") -> bytes:
    if array.ndim == 2:
        array = array[np.newaxis, ...]
    profile = {
        "driver": "GTiff",
        "height": array.shape[1],
        "width": array.shape[2],
        "count": array.shape[0],
        "dtype": dtype,
        "crs": crs,
        "transform": transform,
        "tiled": False,
    }
    if nodata is not None:
        profile["nodata"] = nodata
    with MemoryFile() as memfile:
        with memfile.open(**profile) as dst:
            dst.write(array.astype(dtype))
        return memfile.read()


def read_layer_gtiff_bytes(layer_id: int) -> bytes:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT ST_AsGDALRaster(rast, 'GTiff') FROM imagery_analysisrecord WHERE id = %s",
            [layer_id],
        )
        row = cursor.fetchone()
    return row[0] if row and row[0] is not None else b""


def load_layer_array(layer_id: int):
    raw = read_layer_gtiff_bytes(layer_id)
    if not raw:
        raise ValueError("Layer raster is empty.")
    with MemoryFile(raw) as memfile:
        with memfile.open() as src:
            arr = src.read()
            return arr, src.transform, src.crs, src.nodata


def upsert_layer_raster(layer, gtiff_bytes: bytes):
    with connection.cursor() as cursor:
        cursor.execute(
            '''
            UPDATE imagery_analysisrecord
            SET rast = ST_FromGDALRaster(%s),
                extent = ST_Transform(
                    ST_Envelope(ST_FromGDALRaster(%s))::geometry,
                    4326
                )::geometry(Polygon, 4326)
            WHERE id = %s
            ''',
            [gtiff_bytes, gtiff_bytes, layer.id],
        )


def sample_layer_value(layer_id: int, lon: float, lat: float, band: int = 1):
    with connection.cursor() as cursor:
        cursor.execute(
            '''
            SELECT ST_Value(
                rast,
                %s,
                ST_Transform(ST_SetSRID(ST_MakePoint(%s, %s), 4326), ST_SRID(rast))
            )
            FROM imagery_analysisrecord
            WHERE id = %s
            ''',
            [band, lon, lat, layer_id],
        )
        row = cursor.fetchone()
    return row[0] if row else None

def layer_extent_bounds(layer_id: int):
    with connection.cursor() as cursor:
        cursor.execute(
            '''
            SELECT
                ST_XMin(extent), ST_YMin(extent),
                ST_XMax(extent), ST_YMax(extent)
            FROM imagery_analysisrecord
            WHERE id = %s
            ''',
            [layer_id],
        )
        row = cursor.fetchone()

    if not row or any(v is None for v in row):
        return None

    minx, miny, maxx, maxy = map(float, row)
    return [[miny, minx], [maxy, maxx]]


def hex_to_rgb(color: str):
    color = color.lstrip("#")
    return tuple(int(color[i : i + 2], 16) for i in (0, 2, 4))


def stretch(arr, vmin, vmax, gamma=1.0):
    scaled = (arr - vmin) / max(vmax - vmin, 1e-9)
    scaled = np.clip(scaled, 0, 1)
    if gamma and gamma != 1.0:
        scaled = np.power(scaled, 1.0 / gamma)
    return (scaled * 255).astype("uint8")


def render_single_band_png(array, nodata, style):
    arr = array.astype("float32")
    mask = np.zeros(arr.shape, dtype=bool)
    if nodata is not None:
        mask |= np.isclose(arr, nodata)
    mask |= ~np.isfinite(arr)
    palette = [hex_to_rgb(c) for c in style["palette"]]
    vmin = style["min"]
    vmax = style["max"]
    scaled = np.clip((arr - vmin) / max(vmax - vmin, 1e-9), 0, 1)
    idx = np.floor(scaled * (len(palette) - 1)).astype(int)
    rgb = np.zeros((arr.shape[0], arr.shape[1], 3), dtype="uint8")
    for i, color in enumerate(palette):
        rgb[idx == i] = color
    alpha = np.where(mask, 0, 220).astype("uint8")
    rgba = np.dstack([rgb, alpha])
    image = Image.fromarray(rgba, mode="RGBA")
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def render_rgb_png(array, nodata, style):
    bands = style["bands"]
    mins = style["min"]
    maxs = style["max"]
    gamma = style.get("gamma", 1.0)
    rgb = []
    alpha_mask = np.zeros(array.shape[1:], dtype=bool)
    for band_index, vmin, vmax in zip(bands, mins, maxs):
        band = array[band_index - 1].astype("float32")
        if nodata is not None:
            alpha_mask |= np.isclose(band, nodata)
        alpha_mask |= ~np.isfinite(band)
        rgb.append(stretch(band, vmin, vmax, gamma))
    alpha = np.where(alpha_mask, 0, 220).astype("uint8")
    rgba = np.dstack(rgb + [alpha])
    image = Image.fromarray(rgba, mode="RGBA")
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


import io
import numpy as np
from PIL import Image

from .models import AnalysisRecord

from .models import AnalysisRecord

DISPLAY_MASK_SCALE = 8


def _hex_to_rgb(value: str):
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def _build_palette_lut(palette):
    colors = np.array([_hex_to_rgb(c) for c in palette], dtype=np.float32)
    if len(colors) == 1:
        return np.repeat(colors.astype(np.uint8), 256, axis=0)

    xs = np.linspace(0.0, 1.0, len(colors))
    t = np.linspace(0.0, 1.0, 256)

    lut = np.zeros((256, 3), dtype=np.uint8)
    for ch in range(3):
        lut[:, ch] = np.interp(t, xs, colors[:, ch]).astype(np.uint8)
    return lut


def _upsample_nearest_2d(arr, scale: int):
    if scale <= 1:
        return arr
    return np.repeat(np.repeat(arr, scale, axis=0), scale, axis=1)


def _upsample_nearest_3d(arr, scale: int):
    if scale <= 1:
        return arr
    return np.repeat(np.repeat(arr, scale, axis=1), scale, axis=2)


def _aoi_geometry_in_layer_crs(layer_crs):
    geom = load_aoi_feature()["geometry"]
    dst_crs = layer_crs.to_string() if hasattr(layer_crs, "to_string") else str(layer_crs)

    if dst_crs and dst_crs not in {"EPSG:4326", "OGC:CRS84", "CRS84"}:
        geom = transform_geom("EPSG:4326", dst_crs, geom, precision=-1)

    return geom


def _display_aoi_mask(out_shape, transform, crs):
    aoi_geom = _aoi_geometry_in_layer_crs(crs)
    return geometry_mask(
        [aoi_geom],
        out_shape=out_shape,
        transform=transform,
        invert=True,
        all_touched=False,
    )


def render_layer_png(record_id):
    row = AnalysisRecord.objects.only(
        "analysis_type",
        "style_config",
        "min_value",
        "max_value",
        "nodata",
    ).get(pk=record_id)

    arr, transform, crs, nodata = load_layer_array(record_id)
    style = row.style_config or {}

    scale = DISPLAY_MASK_SCALE
    display_transform = transform * Affine.scale(1.0 / scale, 1.0 / scale)

    if style.get("mode") == "rgb" or row.analysis_type == "rgb":
        display_arr = _upsample_nearest_3d(arr.astype("float32"), scale)
        aoi_mask = _display_aoi_mask(display_arr.shape[1:], display_transform, crs)

        bands = list(style.get("bands") or [1, 2, 3])
        mins = list(style.get("min") or [0.02, 0.02, 0.02])
        maxs = list(style.get("max") or [0.30, 0.30, 0.30])
        gamma = float(style.get("gamma", 1.2) or 1.2)

        rgba_channels = []
        valid_mask = np.ones(display_arr.shape[1:], dtype=bool)

        for band_index, vmin, vmax in zip(bands, mins, maxs):
            band = display_arr[band_index - 1].astype("float32")

            band_valid = np.isfinite(band)
            if nodata is not None:
                band_valid &= ~np.isclose(band, nodata)

            valid_mask &= band_valid

            vmin = float(vmin)
            vmax = float(vmax)
            if vmax <= vmin:
                vmax = vmin + 1e-6

            channel = np.zeros(band.shape, dtype=np.uint8)
            if np.any(band_valid):
                scaled = np.clip((band[band_valid] - vmin) / (vmax - vmin), 0.0, 1.0)
                if gamma != 1.0:
                    scaled = np.power(scaled, 1.0 / gamma)
                channel[band_valid] = (scaled * 255.0).astype(np.uint8)

            rgba_channels.append(channel)

        alpha = np.where(valid_mask & aoi_mask, 255, 0).astype(np.uint8)
        rgba = np.dstack(rgba_channels + [alpha])

        image = Image.fromarray(rgba, mode="RGBA")
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        return buf.getvalue()

    band = arr[0].astype("float32")
    if nodata is not None:
        band = np.where(np.isclose(band, nodata), np.nan, band)

    valid = np.isfinite(band)
    if not np.any(valid):
        return None

    palette = style.get("palette") or ["#000000", "#ffffff"]

    vmin = style.get("min")
    vmax = style.get("max")

    if vmin is None:
        vmin = row.min_value if row.min_value is not None else float(np.nanmin(band))
    if vmax is None:
        vmax = row.max_value if row.max_value is not None else float(np.nanmax(band))

    vmin = float(vmin)
    vmax = float(vmax)
    if vmax <= vmin:
        vmax = vmin + 1e-6

    display_band = _upsample_nearest_2d(band, scale)
    display_valid = _upsample_nearest_2d(valid.astype(np.uint8), scale).astype(bool)
    aoi_mask = _display_aoi_mask(display_band.shape, display_transform, crs)

    idx = np.zeros(display_band.shape, dtype=np.uint8)
    finite = np.isfinite(display_band)
    if np.any(finite):
        scaled = np.clip((display_band[finite] - vmin) / (vmax - vmin), 0.0, 1.0)
        idx[finite] = (scaled * 255.0).astype(np.uint8)

    lut = _build_palette_lut(palette)

    rgba = np.zeros((display_band.shape[0], display_band.shape[1], 4), dtype=np.uint8)
    rgba[..., :3] = lut[idx]
    rgba[..., 3] = np.where(display_valid & aoi_mask, 255, 0).astype(np.uint8)

    image = Image.fromarray(rgba, mode="RGBA")
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()
    