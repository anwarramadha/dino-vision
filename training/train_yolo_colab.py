"""Upload this single file to Google Colab, fill the settings below, then run it."""

import shutil
import subprocess
import sys
from getpass import getpass
from pathlib import Path

# Training settings.
BASE_MODEL = "yolov8n.pt"
EPOCHS = 80
IMAGE_SIZE = 640
BATCH_SIZE = -1  # -1 lets Ultralytics select a suitable batch size.

# Google Drive locations. The dataset is downloaded temporarily to Colab storage.
DATASET_DIRECTORY = Path("/content/dino-dataset")
RUNS_DIRECTORY = Path("/content/runs")
MODEL_OUTPUT = Path("/content/drive/MyDrive/dino-vision/dino-yolo.pt")


def ensure_package(package: str) -> None:
    try:
        __import__(package)
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", package])


def mount_drive() -> None:
    try:
        from google.colab import drive
    except ImportError as error:
        raise RuntimeError("Script ini dirancang untuk dijalankan di Google Colab.") from error
    drive.mount("/content/drive")


def get_dataset_settings() -> tuple[str, str, int]:
    workspace = input("Roboflow workspace: ").strip()
    project = input("Roboflow project: ").strip()
    version_text = input("Roboflow dataset version [1]: ").strip() or "1"
    if not workspace or not project:
        raise ValueError("Roboflow workspace dan project wajib diisi.")
    try:
        version = int(version_text)
    except ValueError as error:
        raise ValueError("Roboflow dataset version harus berupa angka.") from error
    if version < 1:
        raise ValueError("Roboflow dataset version harus bernilai minimal 1.")
    return workspace, project, version


def download_dataset(api_key: str, workspace: str, project: str, version: int) -> Path:
    from roboflow import Roboflow

    dataset = (
        Roboflow(api_key=api_key)
        .workspace(workspace)
        .project(project)
        .version(version)
        .download("yolov8", location=str(DATASET_DIRECTORY))
    )
    data_path = Path(dataset.location) / "data.yaml"
    if not data_path.exists():
        raise FileNotFoundError(f"data.yaml tidak ditemukan: {data_path}")
    return data_path


def main() -> None:
    mount_drive()
    ensure_package("roboflow")
    ensure_package("ultralytics")
    from ultralytics import YOLO

    api_key = getpass("Roboflow API key: ").strip()
    if not api_key:
        raise ValueError("Roboflow API key wajib diisi.")

    workspace, project, version = get_dataset_settings()
    data_path = download_dataset(api_key, workspace, project, version)
    model = YOLO(BASE_MODEL)
    result = model.train(
        data=str(data_path),
        epochs=EPOCHS,
        imgsz=IMAGE_SIZE,
        batch=BATCH_SIZE,
        project=str(RUNS_DIRECTORY),
        name="dino-yolo",
    )

    best_model = Path(result.save_dir) / "weights" / "best.pt"
    if not best_model.exists():
        raise FileNotFoundError(f"Model terbaik tidak ditemukan: {best_model}")

    MODEL_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(best_model, MODEL_OUTPUT)
    print(f"Training selesai. Model terbaik tersimpan di: {MODEL_OUTPUT}")


if __name__ == "__main__":
    main()
