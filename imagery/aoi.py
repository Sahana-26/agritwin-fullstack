import json
from django.conf import settings


def load_aoi_feature():
    with open(settings.AOI_GEOJSON_PATH, 'r', encoding='utf-8') as fh:
        geojson = json.load(fh)
    return geojson['features'][0]