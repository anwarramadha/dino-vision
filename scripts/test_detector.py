import sys
from datetime import datetime
from pathlib import Path

from PIL import ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dino_vision.capture import ScreenCapture
from dino_vision.config import load_settings
from dino_vision.detector import DinoDetector


def main() -> None:
    settings = load_settings()
    frame = ScreenCapture(settings["capture"]).capture()
    detections = DinoDetector(settings["detector"]).detect(frame)

    preview = frame.copy()
    draw = ImageDraw.Draw(preview)
    for detection in detections:
        box = (detection.left, detection.top, detection.right, detection.bottom)
        draw.rectangle(box, outline="red", width=3)
        draw.text(
            (detection.left, max(0, detection.top - 16)),
            f"{detection.label} {detection.confidence:.0%}",
            fill="red",
        )

    output = Path("assets/screenshots") / datetime.now().strftime("detection-%Y%m%d-%H%M%S.png")
    preview.save(output)
    print(f"{len(detections)} deteksi tersimpan di: {output}")
    for detection in detections:
        print(f"- {detection.label}: {detection.confidence:.1%} at x={detection.left:.0f}")


if __name__ == "__main__":
    main()
