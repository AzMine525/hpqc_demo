# HPQC two-way chat demo

**Stage 07** menyediakan `--suite` pada CLI handshake dan transfer v2. Pilih satu suite yang sama di kedua endpoint. Default `ml-kem-768` memakai ID 1 dan kompatibel dengan endpoint v2 Stage 06. [Pilihan suite, format wire, perintah dan bukti pengujian](docs/crypto_agility.md)

**Stage 06** menguji penolakan tampering dan replay, lalu membandingkan pengiriman payload yang sama pada kontrol plaintext dan HPQC v2 melalui TCP loopback. Perintah reproduksi, matriks penerimaan, dua packet capture, dan transkrip regresi tersedia di [laporan pengujian keamanan](docs/security_testing.md).

**Stage 05** mengirim teks UTF-8 atau file biner hingga 1 MiB melalui sesi v2. Kedua arah menggunakan AES-256-GCM dan application ACK yang mencocokkan message ID. Jalankan `python -B -m protocol.transfer_cli --help` untuk opsi. [Panduan transfer, format wire, dan uji dua terminal](docs/secure_data.md)

Stage 04 menyediakan CLI handshake dua arah dengan PSK dan konfirmasi kunci. Panduan pembuatan PSK, perintah client/server, dan format lima pesan ada di [spesifikasi handshake v2](docs/secure_handshake.md).

Crypto Engine Stage 03 tersedia untuk pengujian lokal di paket `crypto_engine.v2`. Chat di bawah menjalankan protokol Stage 02. Lihat [kontrak API, format AAD, dan pengujian Stage 03](docs/crypto_engine.md).

Prototipe penelitian chat TCP dua arah dengan ML-KEM-768, HKDF-SHA512, dan AES-256-GCM. Lihat diagram urutan, tanggung jawab modul, dan format frame di [dokumentasi arsitektur](docs/architecture.md).

## Persiapan

Gunakan Python 3.9+ dengan virtual environment proyek pada setiap mesin. Python 3.11.9 dipakai untuk verifikasi Stage 02 di Windows. Bila venv belum tersedia, buat dengan interpreter yang akan dipakai dan pasang dependency dari `requirements.txt` setelah instalasi disetujui. Salin seluruh source proyek saat menjalankan versi modular di guest, termasuk `crypto_engine/` dan `protocol/`.

### Windows PowerShell

```powershell
python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Jika alias `python` membuka Microsoft Store, ganti pada perintah pembuatan venv dengan path executable Python yang terpasang.

### Ubuntu dan Debian

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
```

## Jalankan dua terminal

Pada Windows, jalankan server dan client secara lokal dari direktori proyek.

```powershell
# Terminal 1
& .\.venv\Scripts\python.exe -B chat.py server --host 127.0.0.1 --port 5050
# Terminal 2
& .\.venv\Scripts\python.exe -B chat.py client --host 127.0.0.1 --port 5050
```

Untuk dua VM pada PQC-LAB, dapatkan IP aktual Debian dengan `ip -br -4 addr`. Set `DEBIAN_IP` pada kedua terminal ke alamat adapter lab Debian.

```bash
# Debian
read -r -p 'IPv4 Debian pada PQC-LAB: ' DEBIAN_IP
./.venv/bin/python -B server.py --host "$DEBIAN_IP" --port 5050
```

```bash
# Ubuntu
read -r -p 'IPv4 Debian pada PQC-LAB: ' DEBIAN_IP
./.venv/bin/python -B client.py --host "$DEBIAN_IP" --port 5050
```

`server.py` dan `client.py` menerima opsi yang sama dengan `chat.py server` dan `chat.py client`. Bandingkan fingerprint SHA-256 di konsol tepercaya, lalu kirim dua pesan berbeda dari tiap terminal. Periksa teks di terminal penerima. Ketik `/quit` untuk keluar. Jika peer masih menunggu input, ketik `/quit` di sana juga. Untuk sesi berikutnya, jalankan kembali server.

## Smoke test dan regresi

Atur `HPQC_BASELINE_ZIP` ke path arsip Stage 00 untuk menjalankan dua uji pasangan versi asli dan versi modular. Suite mencoba path bawaan di bawah dan melewati dua uji campuran bila path bawaan tidak tersedia dan variabel belum diatur. Jika path diberikan secara eksplisit, file yang hilang atau hash `chat.py` yang berbeda membuat uji gagal. Tes memakai TCP loopback pada mesin tempat suite dijalankan. Gunakan Python tanpa `-O` untuk smoke test.

Pada Windows:

```powershell
$env:HPQC_BASELINE_ZIP = (Resolve-Path '..\hpqc_demo_baselines\prototype-original-20261126.zip').Path
& .\.venv\Scripts\python.exe -B smoke_test.py
& .\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

Pada Ubuntu dan Debian, jalankan masing-masing dari root proyek. Sesuaikan path arsip bila salinannya berada di lokasi berbeda.

```bash
export HPQC_BASELINE_ZIP=../hpqc_demo_baselines/prototype-original-20261126.zip
./.venv/bin/python -B smoke_test.py
./.venv/bin/python -B -m unittest discover -s tests -v
```

Untuk prosedur capture yang telah disiapkan bagi prototipe asli, lihat [panduan Stage 01](docs/testing_guide.md). Untuk hash sumber dan prosedur pemulihan arsip, lihat [log pengembangan](PROGRESS.md).

Gunakan hanya di lab penelitian. Fingerprint ditampilkan untuk pemeriksaan manual dan aplikasi melanjutkan handshake otomatis. Indikator `[Terkirim]` menunjukkan pengiriman frame lokal. Angka handshake dan AES adalah durasi lokal yang dicetak per operasi.
