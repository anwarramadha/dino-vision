from pathlib import Path
from typing import Any

import yaml


def load_settings(path: str | Path = "config/settings.yaml") -> dict[str, Any]:
    settings_path = Path(path)
    if not settings_path.exists():
        raise FileNotFoundError(
            f"{settings_path} tidak ditemukan. Salin config/settings.example.yaml terlebih dahulu."
        )

    with settings_path.open(encoding="utf-8") as file:
        settings = yaml.safe_load(file)

    if not isinstance(settings, dict):
        raise ValueError("File konfigurasi harus berisi mapping YAML.")
    return settings
