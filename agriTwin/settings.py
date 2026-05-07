import os
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv
from datetime import timedelta

# ==========================================
# BASE CONFIG
# ==========================================
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')


def env(name, default=None):
    return os.getenv(name, default)


# ==========================================
# GIS LIBRARY PATHS (OPTIONAL / PORTABLE)
# ==========================================

def _first_existing(paths):
    for path in paths:
        if path and Path(path).exists():
            return str(path)
    return None


_gdal_env = env('GDAL_LIBRARY_PATH')
_geos_env = env('GEOS_LIBRARY_PATH')

if os.name == 'nt':
    _gdal_env = _gdal_env or _first_existing([
        r'C:\OSGeo4W\bin\gdal312.dll',
        r'C:\Users\LENOVO\AppData\Local\Programs\OSGeo4W\bin\gdal312.dll',
    ])
    _geos_env = _geos_env or _first_existing([
        r'C:\OSGeo4W\bin\geos_c.dll',
        r'C:\Users\LENOVO\AppData\Local\Programs\OSGeo4W\bin\geos_c.dll',
    ])

if _gdal_env:
    os.environ['GDAL_LIBRARY_PATH'] = _gdal_env
if _geos_env:
    os.environ['GEOS_LIBRARY_PATH'] = _geos_env

GDAL_LIBRARY_PATH = os.environ.get('GDAL_LIBRARY_PATH')
GEOS_LIBRARY_PATH = os.environ.get('GEOS_LIBRARY_PATH')

# ==========================================
# SECURITY
# ==========================================
SECRET_KEY = env('SECRET_KEY', 'django-insecure-change-this')
DEBUG = env('DEBUG', 'True').lower() == 'true'

ALLOWED_HOSTS = [
    h.strip() for h in env('ALLOWED_HOSTS', '192.168.29.12,127.0.0.1,localhost').split(',') if h.strip()
]

# ==========================================
# INSTALLED APPS
# ==========================================
INSTALLED_APPS = [
    'corsheaders',
    'rest_framework',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.gis',
    'imagery',
    'accounts',
    'doctor_ai',
    'farm_data',
    'yield_ai',
]

# ==========================================
# MIDDLEWARE
# ==========================================
MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'agriTwin.urls'

# ==========================================
# TEMPLATES
# ==========================================
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'agriTwin.wsgi.application'
ASGI_APPLICATION = 'agriTwin.asgi.application'

# ==========================================
# DATABASE (POSTGIS)
# ==========================================
DATABASES = {
    'default': {
        'ENGINE': 'django.contrib.gis.db.backends.postgis',
        'NAME': env('DB_NAME', 'agritwin_analysis'),
        'USER': env('DB_USER', 'postgres'),
        'PASSWORD': env('DB_PASSWORD', 'root'),
        'HOST': env('DB_HOST', 'localhost'),
        'PORT': env('DB_PORT', '5432'),
    }
}

# ==========================================
# PASSWORD VALIDATION
# ==========================================
AUTH_PASSWORD_VALIDATORS = []

# ==========================================
# INTERNATIONALIZATION
# ==========================================
LANGUAGE_CODE = 'en-us'
TIME_ZONE = env('TIME_ZONE', 'Asia/Kolkata')
USE_I18N = True
USE_TZ = True

# ==========================================
# STATIC / MEDIA
# ==========================================
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ==========================================
# CORS / API
# ==========================================
CORS_ALLOW_ALL_ORIGINS = env('CORS_ALLOW_ALL_ORIGINS', 'True').lower() == 'true'
CORS_ALLOWED_ORIGINS = [
    item.strip() for item in env('CORS_ALLOWED_ORIGINS', 'http://127.0.0.1:5500,http://localhost:5500,http://127.0.0.1:5173,http://localhost:5173').split(',') if item.strip()
]

REST_FRAMEWORK = {
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
        'rest_framework.renderers.BrowsableAPIRenderer',
    ],
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
    ],
}

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=30),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=30),
    'AUTH_HEADER_TYPES': ('Bearer',),
},


APP_BASE_URL = env('APP_BASE_URL', 'http://127.0.0.1:8000')
FRONTEND_BASE_URL = env('FRONTEND_BASE_URL', 'http://127.0.0.1:5500')
PLANETARY_COMPUTER_STAC = env(
    'PLANETARY_COMPUTER_STAC',
    'https://planetarycomputer.microsoft.com/api/stac/v1'
)

# ==========================================
# AOI / LOCAL TERRAIN CONFIG
# ==========================================
_aoi_env = env('AOI_GEOJSON_PATH')
AOI_GEOJSON_PATH = (
    Path(_aoi_env)
    if _aoi_env and str(_aoi_env).strip()
    else (BASE_DIR / 'aoi.geojson')
)

_local_dem_env = env('LOCAL_DEM_PATH')
LOCAL_DEM_PATH = (
    Path(_local_dem_env)
    if _local_dem_env and str(_local_dem_env).strip()
    else (BASE_DIR / 'dem.tif')
)
DEM_SOURCE_FALLBACK_TO_STAC = env('DEM_SOURCE_FALLBACK_TO_STAC', 'True').lower() == 'true'

# ==========================================
# DATA SOURCES
# ==========================================
SENTINEL2_COLLECTION = 'sentinel-2-l2a'
SENTINEL1_COLLECTION = 'sentinel-1-grd'
DEM_COLLECTION = 'cop-dem-glo-30'

# ==========================================
# TIME CONFIG
# ==========================================
HISTORICAL_START_YEAR = int(env('HISTORICAL_START_YEAR', '2019'))
HISTORICAL_END_YEAR = int(env('HISTORICAL_END_YEAR', '2025'))

FUTURE_START_DATE = datetime.strptime(
    env('FUTURE_START_DATE', '2026-02-01'),
    '%Y-%m-%d'
).date()

# ==========================================
# PROCESSING CONFIG
# ==========================================
SENTINEL2_CLOUD_THRESHOLD = float(env('SENTINEL2_CLOUD_THRESHOLD', '90'))
MAX_ITEMS = int(env('MAX_ITEMS', '120'))
RASTER_NODATA = float(env('RASTER_NODATA', '-9999.0'))
