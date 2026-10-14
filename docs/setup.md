# Setup Lokal

## Konfigurasi area game

Jalankan `python scripts/capture_frame.py` lalu buka PNG di `assets/screenshots/`. Tentukan area game sebagai `left`, `top`, `width`, dan `height`, kemudian isi `capture.region` di `config/settings.yaml`. Model akan menerima area ini saja, bukan seluruh layar.

## Kontrol keyboard pada WSLg

WSL tidak menyediakan perangkat kernel `/dev/uinput` yang dapat digunakan `ydotool`. Project mendeteksi WSL secara otomatis dan memilih `pyautogui`, bukan `ydotool`.

WSLg mengekspos XWayland tanpa file `~/.Xauthority` biasa. `GameControl` otomatis memakai `XAUTHORITY=/dev/null` sebelum memuat `pyautogui`; ini menghindari error `Xlib.error.XauthError` yang sebelumnya muncul.

Pertahankan konfigurasi berikut:

```yaml
control:
  backend: auto
```

Setelah Chrome Dino terfokus, jalankan:

```bash
python scripts/test_controls.py
```

Jika Space tidak memulai game, pastikan Chrome dijalankan sebagai aplikasi GUI di lingkungan WSLg yang sama. Browser Windows yang tidak diekspos sebagai jendela WSLg tidak dapat menerima input X11 dari Python di WSL.

Backend capture `auto` juga memilih CDP pada WSL. Ini mengambil PNG langsung dari tab Chrome dan menghindari frame hitam dari `mss`/WSLg. Pastikan Chrome berjalan dengan remote debugging sebelum menjalankan `capture_frame.py`, `collect_dataset.py`, atau `run_agent.py`.

Untuk loop agen, konfigurasi default memakai screenshot CDP JPEG dengan `optimize_for_speed: true`; ini mengurangi waktu encoding dibanding PNG. Gunakan PNG hanya bila mengumpulkan dataset yang membutuhkan frame lossless.

### Chrome Windows melalui CDP

Jika menggunakan Chrome Windows, gunakan backend Chrome DevTools Protocol (CDP). Ini adalah opsi yang direkomendasikan untuk WSL karena event dikirim langsung ke tab browser, bukan melalui desktop WSLg.

Tutup seluruh proses Chrome terlebih dahulu. Di PowerShell Windows, buka Chrome khusus untuk game dengan profil sementara dan remote debugging:

```powershell
& "$env:ProgramFiles\Google\Chrome\Application\chrome.exe" `
  --remote-debugging-port=9222 `
  --remote-allow-origins=http://127.0.0.1:9222 `
  --user-data-dir="$env:TEMP\dino-vision-chrome" `
  chrome://dino
```

Gunakan profil sementara karena Chrome yang sudah berjalan dapat mengabaikan flag remote debugging. Lalu ubah bagian `control` pada `config/settings.yaml`:

```yaml
control:
  backend: cdp
  cdp_url: http://127.0.0.1:9222
  startup_delay_seconds: 3
  duck_duration_seconds: 0.25
```

Bagian `capture` dapat tetap memakai `backend: auto`, atau dibuat eksplisit:

```yaml
capture:
  backend: cdp
  cdp_url: http://127.0.0.1:9222
```

Instal dependency terbaru di WSL, kemudian uji:

```bash
pip install -r requirements.txt
python scripts/test_controls.py
```

Jika endpoint Chrome tidak dapat dijangkau dari WSL, pastikan Chrome masih terbuka dengan port `9222` dan jalankan `python scripts/test_controls.py` dari distro WSL yang sama.

## Kontrol keyboard pada Ubuntu Wayland native

`pyautogui` memakai X11 dan tidak dapat mengirim input global pada Wayland native. Project memilih `ydotool` bila `WAYLAND_DISPLAY` tersedia di luar WSL.

Paket Ubuntu 22.04 (`ydotool` 0.1.8) membuka `/dev/uinput` secara langsung. Buat grup khusus dan aturan udev agar user dapat memakai perangkat input virtual tanpa menjalankan aplikasi Python sebagai root:

```bash
sudo groupadd --system uinput
sudo usermod -aG uinput "$USER"
sudo tee /etc/udev/rules.d/99-uinput.rules >/dev/null <<'EOF'
KERNEL=="uinput", MODE="0660", GROUP="uinput"
EOF
sudo modprobe uinput
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=misc --sysname-match=uinput
```

Keluar lalu masuk kembali ke sesi desktop agar keanggotaan grup baru aktif. Setelah login kembali, periksa izin berikut; grup harus berupa `uinput` dan user harus anggota grup tersebut:

```bash
stat -c '%A %U %G %n' /dev/uinput
id -nG
```

Pada sesi X11, gunakan `control.backend: pyautogui` atau `auto`.
