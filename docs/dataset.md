# Dataset Roboflow

1. Jalankan `python scripts/collect_dataset.py --interval 0.5` sambil bermain Chrome Dino.
2. Seleksi screenshot yang bervariasi sebelum upload: kecepatan game, mode siang/malam, kaktus tunggal/kelompok, dan posisi burung.
3. Buat project Object Detection di Roboflow dan upload gambar terpilih.
4. Anotasi `cactus` dan `bird`. Kelas `dino` bersifat opsional karena agen hanya perlu melihat obstacle.
5. Buat version dengan split train/valid/test dan export format YOLOv8.

Jangan upload API key Roboflow, screenshot mentah, atau export dataset ke Git. Simpan nomor versi dataset yang dipakai untuk setiap eksperimen training.
