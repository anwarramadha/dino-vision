import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dino_vision.calibration import save_calibration_frame
from dino_vision.capture import ScreenCapture
from dino_vision.config import load_settings


def main() -> None:
    settings = load_settings()
    frame = ScreenCapture(settings["capture"]).capture()
    filename = datetime.now().strftime("frame-%Y%m%d-%H%M%S.png")
    output = save_calibration_frame(frame, Path("assets/screenshots") / filename)
    print(f"Screenshot tersimpan: {output}")
    print(f"Ukuran frame: {frame.width}x{frame.height}")


if __name__ == "__main__":
    main()
