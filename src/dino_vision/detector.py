from pathlib import Path
from typing import Any

from PIL import Image
import torch
from ultralytics import YOLO

from dino_vision.types import Detection


class DinoDetector:
    def __init__(self, settings: dict[str, Any]) -> None:
        torch.set_num_threads(settings.get("inference_threads", 4))
        model_path = Path(settings["model_path"])
        if not model_path.exists():
            raise FileNotFoundError(f"Model tidak ditemukan: {model_path}")
        self.model = YOLO(model_path)
        self.confidence = settings.get("confidence", 0.45)
        self.image_size = settings.get("image_size", 416)
        self.allowed_labels = set(settings.get("classes", []))

    def detect(self, frame: Image.Image) -> list[Detection]:
        result = self.model(
            frame,
            conf=self.confidence,
            imgsz=self.image_size,
            verbose=False,
        )[0]
        labels = result.names
        detections: list[Detection] = []

        for box in result.boxes:
            class_id = int(box.cls.item())
            label = labels[class_id]
            if self.allowed_labels and label not in self.allowed_labels:
                continue
            left, top, right, bottom = box.xyxy[0].tolist()
            detections.append(
                Detection(label, float(box.conf.item()), left, top, right, bottom)
            )
        return detections
