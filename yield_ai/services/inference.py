import os
import numpy as np
import tensorflow as tf
from django.conf import settings

BASE_DIR = settings.BASE_DIR

FEATURE_ORDER = [
    'rainfall',
    'temperature',
    'soil_ph',
    'fertilizer',
    'irrigation_frequency',
    'organic_carbon',
]

MODEL_REGISTRY = {
    'coconut': {
        'label': 'Coconut',
        'model_path': os.path.join(BASE_DIR, 'yield_ai', 'ml_models', 'coconut_model.tflite'),
    },
    'coffee': {
        'label': 'Coffee',
        'model_path': os.path.join(BASE_DIR, 'yield_ai', 'ml_models', 'coffee_model.tflite'),
    },
    'ginger': {
        'label': 'Ginger',
        'model_path': os.path.join(BASE_DIR, 'yield_ai', 'ml_models', 'ginger_model.tflite'),
    },
    'pepper': {
        'label': 'Pepper',
        'model_path': os.path.join(BASE_DIR, 'yield_ai', 'ml_models', 'pepper_model.tflite'),
    },
    'potato': {
        'label': 'Potato',
        'model_path': os.path.join(BASE_DIR, 'yield_ai', 'ml_models', 'potato_model.tflite'),
    },
}

_INTERPRETER_CACHE = {}


def get_interpreter(crop_key: str):
    crop_key = crop_key.lower().strip()

    if crop_key not in MODEL_REGISTRY:
        raise ValueError(f'Unsupported crop: {crop_key}')

    if crop_key not in _INTERPRETER_CACHE:
        model_path = MODEL_REGISTRY[crop_key]['model_path']

        if not os.path.exists(model_path):
            raise FileNotFoundError(f'Model file not found: {model_path}')

        interpreter = tf.lite.Interpreter(model_path=model_path)
        interpreter.allocate_tensors()
        _INTERPRETER_CACHE[crop_key] = interpreter

    return _INTERPRETER_CACHE[crop_key]


def prepare_input_tensor(interpreter, payload: dict):
    values = [float(payload[field]) for field in FEATURE_ORDER]
    input_details = interpreter.get_input_details()[0]

    input_data = np.array(values, dtype=np.float32)

    input_shape = tuple(int(x) for x in input_details['shape'])

    if len(input_shape) == 2:
        input_data = input_data.reshape(1, len(values))
    elif len(input_shape) == 1:
        input_data = input_data.reshape(len(values),)
    else:
        input_data = input_data.reshape(1, len(values))

    target_dtype = input_details['dtype']
    if input_data.dtype != target_dtype:
        input_data = input_data.astype(target_dtype)

    return input_data


def predict_yield(crop_key: str, payload: dict):
    interpreter = get_interpreter(crop_key)

    input_details = interpreter.get_input_details()
    output_details = interpreter.get_output_details()

    input_tensor = prepare_input_tensor(interpreter, payload)

    interpreter.set_tensor(input_details[0]['index'], input_tensor)
    interpreter.invoke()

    output = interpreter.get_tensor(output_details[0]['index'])
    predicted_yield = float(np.array(output).flatten()[0])

    return round(predicted_yield, 2)