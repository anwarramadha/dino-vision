import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dino_vision.config import load_settings
from dino_vision.control import GameControl


def main() -> None:
    try:
        control = GameControl(load_settings()["control"])
    except RuntimeError as error:
        raise SystemExit(f"Kontrol gagal: {error}") from error
    print(f"Fokuskan Chrome Dino. Input dikirim dalam {control.startup_delay} detik.")
    control.wait_for_focus()
    try:
        control.start_or_jump()
    except RuntimeError as error:
        raise SystemExit(f"Kontrol gagal: {error}") from error
    print("Tombol Space terkirim.")


if __name__ == "__main__":
    main()
