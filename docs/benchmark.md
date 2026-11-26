# Stage 08 — Benchmark kriptografi dan komunikasi HPQC

Benchmark menjalankan engine dan protokol v2 produksi menggunakan data sintetis. Kriptografi lokal dan komunikasi dicatat ke CSV masing-masing. Skenario komunikasi menjalankan kedua endpoint di satu proses dan memakai koneksi TCP IPv4 baru pada `127.0.0.1` untuk setiap percobaan. [Pilihan suite dan spesifikasi handshake](crypto_agility.md) · [Format DATA dan ACK](secure_data.md)

## Menjalankan di Windows, Ubuntu, atau Debian

Dari root proyek, gunakan interpreter venv dengan dependency di `requirements.txt`. Pada Windows dapat memakai `& .\.venv\Scripts\python.exe` dari PowerShell. Pada Ubuntu atau Debian dapat memakai `python3` dari environment yang telah disiapkan. Opsi `--output` harus menunjuk ke direktori baru.

```text
python -B -m benchmark.run_experiment --output results/stage08/ulangan --warmup 3 --trials 20
python -B -m unittest discover -s tests -p test_benchmark.py -v
python -B -m unittest discover -s tests -v
python -B smoke_test.py
```

Default mencakup empat suite dan kedua workload. Untuk memilih sebagian, ulangi `--suite` dengan nama suite seperti `ml-kem-768` atau `rsa-2048-oaep`. Gunakan `--mode crypto` atau `--mode network` untuk menjalankan satu workload. `--timeout` menetapkan batas untuk handshake dan timeout socket I/O dalam detik, dengan default 10. PSK dan material sesi eksperimen dibuat di memori. Suite regresi penuh memerlukan arsip prototipe untuk dua skenario interop legacy. [Lokasi arsip](../README.md)

## Urutan percobaan

1. Runner menjalankan seluruh warm-up dahulu, lalu percobaan terukur. Setiap indeks pengulangan mencakup suite terpilih dalam urutan yang tercatat pada manifest. Untuk satu suite, runner menjalankan satu trial kriptografi dan satu koneksi TCP per ukuran payload. Ukuran 1 KiB, 100 KiB, dan 1 MiB berarti 1.024, 102.400, dan 1.048.576 byte.
2. Trial lokal membuat keypair baru, membentuk dan membuka ciphertext, memeriksa agreement secret, menurunkan keempat kunci, lalu menjalankan enkripsi dan dekripsi setiap ukuran dengan `DirectionCipher`. Payload, random konteks HKDF, serta konstruksi objek cipher disiapkan di luar interval masing-masing operasi. Pemeriksaan agreement dan kesetaraan plaintext dilakukan sesudah pengukuran operasi.
3. Trial TCP membuka listener dan mengukur connect, lalu menjalankan handshake dua peran melalui `DataChannel`. Setelah kedua channel siap, client mengirim satu DATA dan menunggu ACK, lalu server melakukan hal yang sama. Setiap delivery diverifikasi dari payload dan ID pada penerima serta ACK terautentikasi dengan ID yang sama pada pengirim.

## Definisi dan sampling

| Metrik | Definisi |
|---|---|
| `keygen_wall`, `encapsulate_wall`, `decapsulate_wall` | Durasi masing-masing pemanggilan backend per trial. Untuk RSA, keygen mencakup serialisasi public key, encapsulate mencakup parsing public key dan CSPRNG untuk secret, serta decapsulate mencakup pembukaan OAEP. |
| `hkdf_wall`, `aes_encrypt_wall`, `aes_decrypt_wall` | Durasi satu key schedule empat kunci dan tiap operasi AES-GCM per ukuran. Operasi AES mencakup pembentukan AAD dan tracking nonce, termasuk pembuatan nonce pada enkripsi. |
| `tcp_connect` | Durasi `connect()` pada sisi client, sesudah listener siap. |
| `handshake` | Dari tepat sebelum client memulai `DataChannel` sampai kedua channel siap. Termasuk handshake, penjadwalan worker, dan inisialisasi cipher sesi. |
| `handshake_wire` | Jumlah byte yang berhasil ditulis oleh kedua endpoint selama handshake, termasuk lima prefix frame. Counter diambil sebelum DATA dikirim. |
| `application_rtt` | Durasi dari sebelum `send_data()` hingga `receive()` pada pengirim mengembalikan ACK. Timestamp pada satu endpoint memakai satu clock. Keberhasilan RTT dan goodput bergantung pada pemeriksaan isi di penerima. |
| `goodput` | Byte payload dibagi RTT dalam detik, per arah, dengan satu pesan menunggu ACK. |
| `delivery_success` | Bernilai 1 jika payload dan ACK terverifikasi, 0 jika kondisi itu gagal tercapai. Mean per arah adalah proporsi sukses dari seluruh trial terukur, termasuk trial yang berhenti sebelum DATA. |
| `tcp_retransmissions` | Penghitung segmen yang ditransmisi ulang per socket pengirim menurut Linux TCP_INFO. Pembacaan sekali per endpoint setelah kedua transfer mencakup masa hidup koneksi hingga saat itu, termasuk handshake. Windows menghasilkan nilai kosong dengan status `unavailable`. [Linux UAPI `tcp_info`](https://raw.githubusercontent.com/torvalds/linux/master/include/uapi/linux/tcp.h) |
| `*_cpu`, `*_rss_before`, `*_rss_after` | CPU adalah selisih `process_time_ns()` dalam ns. RSS dibaca dengan `psutil.Process.memory_info()` pada awal dan akhir operasi dalam byte. `network_session_*` mencakup setup listener, kedua endpoint dan worker, handshake, kedua transfer, serta cleanup. RSS adalah dua snapshot seluruh proses. [Referensi psutil](https://psutil.readthedocs.io/en/latest/) |

Durasi wall memakai `perf_counter_ns()`. Proses yang sama menjalankan kedua peran TCP, sehingga CPU jaringan menggabungkan pekerjaan keduanya. RSS juga mencakup interpreter dan alokasi yang sudah ada. Puncak memori di antara dua snapshot dapat terlewat. Startup loopback, scheduling thread, penggunaan daya, dan beban host dapat memengaruhi hasil.

## Cara membaca bukti

- `crypto_raw.csv` dan `network_raw.csv` memuat fase, indeks trial, suite, ukuran, arah, nama metrik, unit, status dan nilai. `payload_bytes=0` menandai metrik kriptografi yang tidak bergantung pada ukuran payload. Baris `trial` mencatat status akhir dan kelas kegagalan. Metrik yang sempat selesai tetap tercatat jika fase berikutnya gagal. Runner mengekspor hasil dan memberi exit 1 jika ada trial gagal. [Data kriptografi](../results/stage08/windows-loopback-02/crypto_raw.csv) · [Data komunikasi](../results/stage08/windows-loopback-02/network_raw.csv)
- `summary.csv` mengelompokkan fase terukur menurut workload, suite, ukuran, arah, metrik, dan unit. Mean aritmetika, median, simpangan baku sampel dengan penyebut `n−1`, dan p95 nearest-rank (`ceil(0,95 × n)` pada urutan naik) dihitung atas nilai tersedia. SD kosong untuk satu sampel, semua angka statistik kosong jika `n=0`, dan `unavailable` mencatat banyaknya sampel dengan status tersebut. [Ringkasan CSV](../results/stage08/windows-loopback-02/summary.csv)
- `manifest.json` memuat command, waktu UTC, host, platform, versi interpreter/dependency, hash source, suite, ukuran, warm-up, dan jumlah percobaan. [Manifest run](../results/stage08/windows-loopback-02/manifest.json)

Untuk skripsi, gunakan ukuran handshake sebagai biaya wire dan RTT/goodput sebagai hasil DATA/ACK pada koneksi yang telah terkonfirmasi. Keygen, HKDF, dan AES dapat dianalisis terpisah dengan dataset lokal. Pengujian host ini memberi bukti loopback. Performa antarperangkat, pengaruh impairment jaringan, dan pengukuran TCP_INFO pada guest memerlukan run tersendiri.
