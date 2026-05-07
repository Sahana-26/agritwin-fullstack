import json
import os
import numpy as np
from PIL import Image
import tensorflow as tf
from django.conf import settings

BASE_DIR = settings.BASE_DIR

MODEL_REGISTRY = {
    "coffee": {
        "model_path": os.path.join(BASE_DIR, "doctor_ai", "ml_models", "coffee_model.tflite"),
        "labels_path": os.path.join(BASE_DIR, "doctor_ai", "ml_models", "coffee_labels.json"),
        "input_size": (128, 128),
    },
}

_INTERPRETERS = {}
_LABELS = {}

def load_labels(labels_path):
    with open(labels_path, "r", encoding="utf-8") as f:
        label_to_index = json.load(f)
    index_to_label = {int(v): k for k, v in label_to_index.items()}
    return index_to_label

def get_interpreter(crop_key):
    if crop_key not in MODEL_REGISTRY:
        raise ValueError(f"Unsupported crop: {crop_key}")

    if crop_key not in _INTERPRETERS:
        model_path = MODEL_REGISTRY[crop_key]["model_path"]
        interpreter = tf.lite.Interpreter(model_path=model_path)
        interpreter.allocate_tensors()
        _INTERPRETERS[crop_key] = interpreter

    if crop_key not in _LABELS:
        labels_path = MODEL_REGISTRY[crop_key]["labels_path"]
        _LABELS[crop_key] = load_labels(labels_path)

    return _INTERPRETERS[crop_key], _LABELS[crop_key]

def preprocess_image(image_file, crop_key):
    config = MODEL_REGISTRY[crop_key]
    input_size = config["input_size"]

    image = Image.open(image_file).convert("RGB")
    image = image.resize(input_size)

    img_array = np.array(image).astype("float32") / 255.0
    img_array = np.expand_dims(img_array, axis=0)  # (1, 128, 128, 3)

    return img_array

def predict_image(image_file, crop_key):
    interpreter, labels = get_interpreter(crop_key)

    input_details = interpreter.get_input_details()
    output_details = interpreter.get_output_details()

    input_data = preprocess_image(image_file, crop_key)
    interpreter.set_tensor(input_details[0]["index"], input_data)
    interpreter.invoke()

    output = interpreter.get_tensor(output_details[0]["index"])[0]

    predicted_index = int(np.argmax(output))
    confidence = float(output[predicted_index]) * 100.0
    predicted_label = labels.get(predicted_index, f"Class {predicted_index}")

    return {
        "crop": crop_key,
        "prediction": predicted_label,
        "predicted_index": predicted_index,
        "confidence": round(confidence, 2),
        "all_scores": [round(float(x) * 100.0, 2) for x in output],
    }

YIELD_ESTIMATION_RULES = {
    "Healthy": 100,
    "Cerscospora": 75,
    "Rust": 65,
    "Phoma": 70,
    "Miner": 80,
}

def get_yield_estimation(prediction_label):
    return YIELD_ESTIMATION_RULES.get(prediction_label, None)
