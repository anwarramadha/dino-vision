# Training di Google Colab

Tidak perlu clone atau `git pull`. Upload satu file `training/train_yolo_colab.py` ke Google Colab.

1. Di panel Files Colab, upload `train_yolo_colab.py`.
2. Jalankan satu cell berikut:

```python
%run /content/train_yolo_colab.py
```

Script akan meminta Roboflow API key secara tersembunyi, lalu workspace, project, dan versi dataset. Setelah itu script mount Google Drive, download dataset YOLOv8 dari Roboflow, menginstal dependensi, dan menjalankan training.

Model terbaik otomatis disimpan di:

```text
/content/drive/MyDrive/dino-vision/dino-yolo.pt
```

Ubah `EPOCHS`, `IMAGE_SIZE`, `BATCH_SIZE`, atau `MODEL_OUTPUT` di bagian atas file jika diperlukan. Unduh model tersebut lalu simpan sebagai `models/dino-yolo.pt` untuk dipakai oleh `scripts/run_agent.py`.
