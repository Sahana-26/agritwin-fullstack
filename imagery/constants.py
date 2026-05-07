from datetime import date

SEASONS = {
    'Pre-Monsoon': {'start': (2, 1), 'end': (5, 31)},
    'Monsoon': {'start': (6, 1), 'end': (9, 30)},
    'Post-Monsoon': {'start': (10, 1), 'end': (11, 30)},
    'Winter': {'start': (12, 1), 'end': (1, 31)},
}

THEME_LABELS = [
    'Vegetation Health',
    'Vegetation Change (Anomaly)',
    'Moisture Condition',
    'Water Retention Opportunity',
    'Agri Suitability (Coconut)',
    'Agri Suitability (Pepper)',
    'Eco-Stay Suitability',
    'Woodland Suitability (Sandalwood)',
    'Rainwater Harvesting Suitability',
    'All-Weather Radar View',
    'Terrain: Elevation',
    'Terrain: Slope',
]

LAYER_BY_THEME = {
    'Vegetation Health': 'ndvi',
    'Vegetation Change (Anomaly)': 'ndvi_anomaly',
    'Moisture Condition': 'ndmi',
    'Water Retention Opportunity': 'waterlite',
    'Agri Suitability (Coconut)': 'coconut',
    'Agri Suitability (Pepper)': 'pepper',
    'Eco-Stay Suitability': 'mudcottage',
    'Woodland Suitability (Sandalwood)': 'sandalwood',
    'Rainwater Harvesting Suitability': 'waterharvesting',
    'All-Weather Radar View': 'radar',
    'Terrain: Elevation': 'dem',
    'Terrain: Slope': 'slope',
}

LAYER_GUIDES = {
    'Vegetation Health': 'Measures live vegetation. Green = healthy; Brown = bare or stressed.',
    'Vegetation Change (Anomaly)': 'Compares current NDVI against previous years of the same season.',
    'Moisture Condition': 'Higher values indicate wetter vegetation and surface moisture.',
    'Water Retention Opportunity': 'Highlights flatter, wetter, lower zones suitable for water storage.',
    'Agri Suitability (Coconut)': 'Favours flatter ground with stronger moisture retention.',
    'Agri Suitability (Pepper)': 'Favours moderate slopes, healthy vegetation, and good drainage.',
    'Eco-Stay Suitability': 'Favours flatter, drier land safer from waterlogging.',
    'Woodland Suitability (Sandalwood)': 'Favours moderate slopes and good drainage.',
    'Rainwater Harvesting Suitability': 'Favours flatter, wetter basins and depressions.',
    'All-Weather Radar View': 'Radar fallback when optical imagery is not usable.',
    'Terrain: Elevation': 'Elevation derived from local dem.tif when available, otherwise Copernicus DEM.',
    'Terrain: Slope': 'Slope derived from local dem.tif when available, otherwise Copernicus DEM.',
}

PALETTES = {
    'ndvi': ['#a50026', '#d73027', '#f46d43', '#fdae61', '#fee08b', '#d9ef8b', '#a6d96a', '#66bd63', '#1a9850', '#006837'],
    'ndvi_anomaly': ['#d73027', '#f46d43', '#ffffff', '#a6d96a', '#1a9850'],
    'ndmi': ['#8c510a', '#d8b365', '#f6e8c3', '#c7eae5', '#5ab4ac', '#01665e'],
    'waterlite': ['#fff7ec', '#fee8c8', '#fdbb84', '#e34a33', '#b30000'],
    'coconut': ['#ffffe5', '#f7fcb9', '#d9f0a3', '#addd8e', '#78c679', '#41ab5d', '#238443', '#005a32'],
    'pepper': ['#e5f5e0', '#c7e9c0', '#a1d99b', '#74c476', '#41ab5d', '#238b45', '#006d2c', '#00441b'],
    'mudcottage': ['#f5f5f5', '#f6e8c3', '#dfc27d', '#bf812d', '#8c510a', '#543005'],
    'sandalwood': ['#f5f5f5', '#c7eae5', '#80cdc1', '#35978f', '#01665e', '#003c30'],
    'waterharvesting': ['#f7fbff', '#c6dbef', '#6baed6', '#2171b5', '#08306b'],
    'dem': ['#edf8fb', '#b3cde3', '#8c96c6', '#88419d'],
    'slope': ['#edf8e9', '#bae4b3', '#74c476', '#238b45', '#005a32'],
}

STYLE_CONFIGS = {
    'rgb': {'mode': 'rgb', 'bands': [1, 2, 3], 'min': [0.02, 0.02, 0.02], 'max': [0.30, 0.30, 0.30], 'gamma': 1.2},
    'radar': {'mode': 'rgb', 'bands': [1, 2, 3], 'min': [-15, -25, 0], 'max': [0, -5, 15], 'gamma': 1.1},
    'ndvi': {'mode': 'single', 'min': 0.1, 'max': 0.85, 'palette': PALETTES['ndvi']},
    'ndvi_anomaly': {'mode': 'single', 'min': -0.15, 'max': 0.15, 'palette': PALETTES['ndvi_anomaly']},
    'ndmi': {'mode': 'single', 'min': -0.2, 'max': 0.5, 'palette': PALETTES['ndmi']},
    'awei': {'mode': 'single', 'min': -2, 'max': 2, 'palette': PALETTES['waterlite']},
    'waterlite': {'mode': 'single', 'min': 0, 'max': 1, 'palette': PALETTES['waterlite']},
    'coconut': {'mode': 'single', 'min': 0, 'max': 1, 'palette': PALETTES['coconut']},
    'pepper': {'mode': 'single', 'min': 0, 'max': 1, 'palette': PALETTES['pepper']},
    'mudcottage': {'mode': 'single', 'min': 0, 'max': 1, 'palette': PALETTES['mudcottage']},
    'sandalwood': {'mode': 'single', 'min': 0, 'max': 1, 'palette': PALETTES['sandalwood']},
    'waterharvesting': {'mode': 'single', 'min': 0, 'max': 1, 'palette': PALETTES['waterharvesting']},
    'dem': {'mode': 'single', 'min': 700, 'max': 950, 'palette': PALETTES['dem']},
    'slope': {'mode': 'single', 'min': 0, 'max': 35, 'palette': PALETTES['slope']},
}
