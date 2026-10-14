import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dino_vision.capture import ScreenCapture
from dino_vision.config import load_settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Kumpulkan screenshot untuk anotasi Roboflow.")
    parser.add_argument("--interval", type=float, default=0.5, help="Jeda antar screenshot dalam detik.")
    parser.add_argument("--limit", type=int, default=0, help="Jumlah frame; 0 berarti tanpa batas.")
    parser.add_argument("--output", type=Path, default=Path("data/raw"))
    args = parser.parse_args()
    if args.interval <= 0:
        parser.error("--interval harus lebih dari 0.")

    args.output.mkdir(parents=True, exist_ok=True)
    capture = ScreenCapture(load_settings()["capture"])
    print("Mulai capture. Tekan Ctrl+C untuk berhenti.")
    count = 0
    try:
        while not args.limit or count < args.limit:
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            capture.capture().save(args.output / f"dino-{timestamp}.png")
            count += 1
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    print(f"{count} screenshot tersimpan di {args.output}")


if __name__ == "__main__":
    main()
