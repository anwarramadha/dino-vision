from pathlib import Path

from PIL import Image


def save_calibration_frame(frame: Image.Image, output_path: str | Path) -> Path:
    """Save an unmodified frame so its pixel coordinates can define the game ROI."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.save(path)
    return path
