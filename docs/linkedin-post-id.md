# Mengontrol Chrome Dino dengan Computer Vision, YOLOv8, dan Python

Saya membuat eksperimen kecil untuk menjawab pertanyaan sederhana: apakah game Chrome Dino bisa dimainkan otomatis menggunakan computer vision?

Target awalnya bukan membuat agent yang sempurna, melainkan membangun pipeline end-to-end:

```text
Screenshot game -> Deteksi obstacle -> Prediksi gerakan -> Jump atau duck
```

## Membuat Dataset Sendiri

Saya memilih membuat dataset sendiri agar model mengenali kondisi game yang benar-benar digunakan saat runtime.

Prosesnya:

1. Merekam permainan Chrome Dino di layar.
2. Mengambil dan memilih frame screenshot.
3. Mengunggah sekitar 300 gambar ke Roboflow.
4. Memberi anotasi bounding box untuk kelas `cactus` dan `bird`.
5. Melatih YOLOv8 di Google Colab.

Model terbaik kemudian digunakan di project Python sebagai `models/dino-yolo.pt`.

## Tantangan Utama: WSL dan Chrome Windows

Project dijalankan dari WSL, sedangkan Chrome berjalan di Windows. Karena itu, pendekatan desktop automation biasa seperti screenshot global dan keyboard global tidak cukup andal.

Saya menggunakan Chrome DevTools Protocol (CDP) untuk:

- Mengambil screenshot langsung dari tab `chrome://dino`.
- Mengirim event keyboard `Space` dan `ArrowDown` langsung ke Chrome.
- Mengecek status game, misalnya apakah game sedang berjalan atau sudah `GAME OVER`.
- Menjaga game tetap aktif walaupun terminal menjadi jendela yang sedang fokus.

Dengan pendekatan ini, agent tidak bergantung pada posisi mouse atau fokus window desktop.

## Dari Deteksi ke Keputusan

Deteksi YOLO saja belum cukup. Agent perlu menentukan kapan obstacle sudah cukup dekat untuk dilompati.

Awalnya saya memakai threshold jarak statis. Masalahnya, kecepatan Chrome Dino terus meningkat. Threshold yang cocok di awal permainan menjadi terlambat saat game lebih cepat.

Policy kemudian dikembangkan menggunakan time-to-collision (TTC):

```text
speed = perubahan posisi obstacle / waktu
TTC = jarak obstacle / speed
```

Agent menyimpan history posisi beberapa frame untuk setiap obstacle, menghitung kecepatannya, lalu memprediksi posisi obstacle saat input keyboard benar-benar sampai ke game.

Policy juga mempertimbangkan:

- Cactus dan bird memiliki aksi berbeda: `jump` atau `duck`.
- Cactus besar menggunakan trigger yang lebih dekat.
- Dua obstacle yang berdekatan diperlakukan sebagai cluster sehingga jump dipicu lebih awal.
- Setiap obstacle memiliki track sendiri agar satu jump tidak menonaktifkan tracking obstacle berikutnya.
- Dino tidak menerima jump kedua ketika masih berada di udara.

## Mengukur Bottleneck

Salah satu pelajaran terpenting dari eksperimen ini: model inference bukan selalu bottleneck utama.

Saya menambahkan telemetry untuk mengukur latency per proses:

```text
CDP game state -> Screenshot capture -> YOLO inference -> Policy -> Keyboard input
```

Hasilnya menunjukkan bahwa screenshot capture melalui CDP sering lebih mahal daripada inferensi YOLO.

Optimasi yang dilakukan:

- Menggunakan JPEG dengan `optimizeForSpeed` untuk screenshot runtime.
- Memakai ROI agar Dino sendiri tidak ikut masuk ke area deteksi.
- Menyesuaikan input YOLO ke `416`, karena `320` membuat cactus kecil gagal terdeteksi pada ROI yang lebar.
- Mengatur jumlah thread inference CPU.
- Menyimpan preview debug secara berkala, bukan setiap frame.

## Eksperimen OpenVINO

Saya juga mencoba export model ke OpenVINO. Secara teori, OpenVINO seharusnya optimal untuk CPU Intel.

Namun benchmark pada environment ini justru menunjukkan PyTorch lebih cepat:

```text
PyTorch .pt:  average 25ms
OpenVINO CPU: average 47ms
```

Ini mengingatkan bahwa optimasi harus selalu diukur. OpenVINO tidak otomatis lebih cepat untuk setiap model, terutama untuk YOLOv8 kecil, batch size 1, dan runtime WSL.

## Pelajaran yang Didapat

- Buat dataset yang representatif terhadap kondisi runtime.
- Deteksi object adalah awal, bukan akhir. Decision policy sama pentingnya.
- Latency capture, inference, dan input harus diukur secara terpisah.
- Prediksi gerakan lebih relevan daripada threshold posisi statis untuk objek yang bergerak cepat.
- Optimasi yang terlihat bagus secara teori harus tetap divalidasi dengan benchmark nyata.

Eksperimen ini masih jauh dari selesai, tetapi pipeline screenshot -> YOLO -> tracking -> action sudah berjalan end-to-end.

Langkah berikutnya adalah meningkatkan kestabilan tracking multi-object dan menurunkan latency capture agar keputusan jump terlihat lebih natural.

#Python #ComputerVision #YOLOv8 #MachineLearning #Roboflow #GoogleColab #ChromeDino #ArtificialIntelligence #Automation
