# Dino Vision

Kontrol Chrome Dino menggunakan screenshot, model YOLO, dan input keyboard Python.

## MVP lokal

1. Buat virtual environment dan instal dependensi:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. Salin konfigurasi dan sesuaikan area game (`region`) pada `config/settings.yaml`:

   ```bash
   cp config/settings.example.yaml config/settings.yaml
   ```

3. Buka `chrome://dino`, lalu ambil screenshot:

   ```bash
   python scripts/capture_frame.py
   ```

4. Dengan jendela Chrome terfokus, uji input keyboard:

   ```bash
   python scripts/test_controls.py
   ```

5. Setelah model tersedia di `models/dino-yolo.pt`, jalankan agen:

   ```bash
   python scripts/test_detector.py
   python scripts/run_agent.py
   ```

`test_detector.py` menyimpan screenshot dengan bounding box YOLO tanpa mengirim input ke game. Jalankan ini sebelum agen untuk memvalidasi model dan area capture.

Untuk menyimpan preview hasil inferensi agen saat debugging, gunakan `python scripts/run_agent.py --save-interval 0.1`. Preview memuat bounding box, label, confidence, dan aksi yang dipilih. Nilai interval dapat berupa pecahan detik; default `0` tidak menyimpan frame agar inferensi tetap cepat.

Untuk melihat deteksi dan keputusan policy dalam terminal, gunakan `python scripts/run_agent.py --log-interval 0.5`. Log menampilkan label, confidence, koordinat, aksi yang diusulkan (`proposed`), dan aksi yang benar-benar dikirim (`sent`).

Bagian `latency_ms` memecah waktu per proses: `state` (status game CDP), `capture` (screenshot CDP), `inference` (YOLO/OpenVINO), `policy`, `input` (keyboard CDP), `verify` (status Dino setelah input), dan `save` (preview debug). `decision_age` adalah umur frame dari selesai capture hingga keputusan dibuat.

Secara default agen tidak mengirim Space saat mulai, sehingga tidak memicu lompatan awal. Mulai game secara manual, atau tambahkan `--start-game` untuk memulai atau mengulang game otomatis.

Tekan `Ctrl+C` untuk menghentikan agen. Backend `auto` memilih `pyautogui` pada WSLg dan `ydotool` pada Wayland native. Untuk Chrome Windows dari WSL, gunakan backend `cdp` sesuai `docs/setup.md`.

## Alur dataset dan training

Ambil screenshot sendiri dengan `scripts/collect_dataset.py`, anotasi dan versioning di Roboflow, kemudian jalankan `training/train_yolo_colab.py` di Google Colab. Unduh `best.pt` hasil training dan letakkan sebagai `models/dino-yolo.pt`.

Dokumentasi lengkap tersedia di `docs/dataset.md` dan `docs/training.md`.
