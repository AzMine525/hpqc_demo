# Stage 06 — Pengujian keamanan dan bukti paket

Pengujian 26 November 2026 memakai dua endpoint TCP milik eksperimen di `127.0.0.1` pada host Windows. Pertanyaannya ada dua. Apakah payload dan ACK yang sah diterima, sementara input yang melanggar protokol ditolak? Apakah marker yang dapat ditemukan pada kontrol plaintext masih terlihat di stream HPQC ketika penerima memperoleh payload yang sama?

## Bukti dan versi

Git HEAD saat pengujian adalah `f181af3aff2b8c0a1412b43c72dec9e67d652183` pada branch `main`. Commit ini mengidentifikasi aplikasi dan spesifikasi yang diuji. Alat eksperimen dan tes tambahan berada di working tree. Host memakai CPython 3.11.9, pqcrypto 1.0.0, dan cryptography 49.0.0. Format pembanding mengikuti [handshake v2](secure_handshake.md) dan [spesifikasi DATA/ACK](secure_data.md).

| Berkas | SHA-256 saat pengujian |
|---|---|
| [Runner eksperimen](../experiments/security_baseline.py) | `afeca179f000517b16f7a9f88094a8ad9cbfeaea834328b99db70079a5417757` |
| [Perekam dan pembaca PCAP](../experiments/loopback_pcap.py) | `1d95a03bc7e28f8eef754c35783733e03ddc17fd2d57509ccfa9cf6bd2c03925` |
| [Tes tambahan](../tests/test_security_evidence.py) | `b52845368fe31c577f3dfcd0907b49db8363eb5bfde263b8a5f6b2ad068abe91` |
| [Transkrip 63 tes](../results/security/test-results.txt) | `83faec2d5e9fdbd45f291bd0dc7e128b32039b1e2940c1ebeaea498a77e4668a` |
| [PCAP plaintext](../results/security/capture-01/plaintext.pcap) | `1ad1677f7099208fa06da84985cf2f6d9f68cb7a372f9fbf832925db0a4befc7` |
| [PCAP HPQC](../results/security/capture-01/secure.pcap) | `9437d8d352d0d05da5042da11bc0a9ea6693c2852833872723203ed146420257` |

Kedua PCAP mentah tersimpan lokal dan diabaikan Git sesuai aturan proyek. Ringkasan memuat waktu mulai UTC, port dalam urutan client lalu server, hash stream per arah, panjang body per frame, dan hasil pemeriksaan penerima. [Manifest capture](../results/security/capture-01/summary.json) · [Run terpisah tanpa capture](../results/security/socket-01/summary.json)

## Metode dan hasil capture

1. Runner membentuk koneksi plaintext khusus eksperimen. Client dan server masing-masing mengirim satu payload sintetis sepanjang 1.024 byte dengan prefix panjang 4 byte. Marker ASCII masing-masing adalah `HPQC-STAGE06-CLIENT-MARKER` dan `HPQC-STAGE06-SERVER-MARKER`, dengan padding titik. Kedua penerima membandingkan seluruh payload.
2. Pada koneksi terpisah, kedua endpoint menjalankan `DataChannel` produksi dengan PSK acak 32 byte dalam memori. Setelah handshake, client mengirim DATA dan server mengonfirmasi, lalu server mengirim DATA dan client mengonfirmasi. Setiap pengirim memeriksa ID pada ACK terautentikasi. Pembanding plaintext hanya ada di runner.
3. Sebelum TCP connect, perekam membuka socket IPv4 loopback dalam mode `RCVALL_IPLEVEL`. Hanya paket TCP dengan kedua alamat loopback dan pasangan port eksperimen yang ditulis ke PCAP. Mode ini membutuhkan akses administrator di Windows. Waktu paket dicatat ketika proses membaca paket. [Dokumentasi Winsock](https://learn.microsoft.com/en-us/windows/win32/winsock/sio-rcvall)
4. Setelah penutupan socket, alat membaca kembali file PCAP dan menyusun stream menurut sequence TCP relatif terhadap SYN masing-masing arah. Ia menolak celah dan byte tumpang tindih yang bertentangan. Syarat lulus mencakup kecocokan setiap byte dengan data yang dikirim endpoint, ukuran dan urutan frame yang benar, jumlah marker sesuai kontrol, serta pemeriksaan penerima di langkah 1–2.

| Run pukul 15.49 WIB | Paket IPv4/TCP | Byte stream client → server | Byte stream server → client | Marker pada stream | Delivery |
|---|---:|---:|---:|---|---|
| Plaintext, port server 53644 | 9 | 1.028 | 1.028 | Marker pengirim muncul sekali pada masing-masing arah | Kedua payload cocok |
| HPQC v2, port server 53646 | 25 | 2.392 | 2.496 | Kedua marker muncul 0 kali pada kedua arah | Kedua payload dan kedua ACK cocok |

Pada stream HPQC terukur 4.888 byte. Lima frame handshake memakai 2.520 byte, dua DATA masing-masing 1.104 byte, dan dua ACK masing-masing 80 byte. Panjang body per arah tercantum dalam manifest dan mengecualikan prefix empat byte. Batas paket TCP dapat berbeda pada pengulangan. Paket IP, header TCP, dan retransmisi dikecualikan dari hitungan byte stream.

## Matriks penerimaan

Nama tes di bawah dapat dicari dalam transkrip lengkap. Kasus negatif menggunakan fixture milik pengujian pada batas decoder atau pasangan socket lokal. PCAP mendokumentasikan dua transfer positif.

| Kriteria | Bukti aktual Windows | Status |
|---|---|---|
| Handshake sah dan penolakan autentikasi | `test_five_frames_proofs_and_key_schedule_against_wire_spec`, `test_wrong_psk`, `test_transcript_and_proof_tampering`, `test_implicit_rejection_detected_at_client_finished` dan pemeriksaan suite | PASS |
| DATA dan ACK sah dua arah | Perbandingan payload dan ID ACK pada capture, `test_simultaneous_bidirectional_binary_sizes` mencakup 1 KiB, 100 KiB dan 1 MiB | PASS |
| Perubahan header, ciphertext, tag DATA atau tag ACK | `test_altered_record_fields_ciphertext_and_tag` memeriksa penolakan, penutupan, sequence tetap, dan jumlah ACK tetap. `test_ack_with_altered_tag_never_confirms_delivery` memeriksa ID masih menunggu konfirmasi | PASS |
| Replay langsung dan lintas sesi | `test_replay_and_cross_session` menguji record lama pada sesi asal dan sesi baru | PASS |
| Record kedaluwarsa dan duplikat | `test_old_data_after_three_deliveries` menyajikan kembali DATA pertama setelah tiga delivery. Sequence penerima tetap 3 dan jumlah ACK tetap 3. `test_authenticated_but_duplicate_message_id_or_nonce` memeriksa ID/nonce berulang dengan tag valid | PASS |
| Record mendahului urutan | `test_future_sequence_with_valid_tag_and_invalid_record_shapes` memeriksa sequence mendatang dengan tag valid | PASS |
| Frame terpotong, terlalu besar, atau salah bentuk | `test_malformed_lengths_and_truncation` dan tes bentuk record di atas mencakup EOF, batas panjang, tipe tak dikenal, dan panjang ACK salah | PASS |
| Kontrol plaintext, integritas capture, dan keterlacakan | Dua PCAP cocok dengan stream endpoint. Tes reassembly mencakup retransmisi, urutan segmen terbalik, wrap, celah dan overlap bertentangan. Hash dan versi tercantum di atas | PASS |

## Mengulang di Windows

Dari root repositori, gunakan interpreter yang telah memiliki dependency proyek. Pada host penelitian, blok berikut memakai interpreter dan dependency yang dipakai pada pengujian aktual. Variabel TEMP dibatasi pada proses PowerShell agar file temporer tes berada di workspace. Untuk venv dengan dependency yang sudah tersedia, gunakan executable venv sebagai `$py` dan lewati pengaturan PYTHONPATH.

```powershell
$py = "$env:LOCALAPPDATA\Python\pythoncore-3.11-64\python.exe"
$env:PYTHONPATH = Join-Path $env:TEMP 'hpqc-stage02-deps-20261126'
$tempUji = New-Item -ItemType Directory -Force __pycache__
$env:TMPDIR = $tempUji.FullName
$env:TMP = $tempUji.FullName
$env:TEMP = $tempUji.FullName
& $py -B smoke_test.py
& $py -B -m unittest discover -s tests -p test_security_evidence.py -v
& $py -B -m unittest discover -s tests -v
& $py -B -m experiments.security_baseline --output results/security/socket-ulangan
```

Untuk capture, jalankan perintah berikut dari PowerShell dengan hak administrator yang disetujui dan interpreter yang sama. Gunakan nama direktori baru untuk tiap run. Kedua direktori output sengaja dibuat eksklusif agar run lama tetap dapat diperiksa.

```powershell
& $py -B -m experiments.security_baseline --windows-capture --output results/security/capture-ulangan
Get-FileHash results/security/capture-ulangan/*.pcap -Algorithm SHA256
```

## Mengulang di Ubuntu atau Debian

Status kedua guest **NOT RUN**. Jalankan secara manual dari root proyek pada masing-masing guest dengan environment Python yang sudah disiapkan. Pengujian interoperabilitas legacy dalam suite lengkap juga membutuhkan arsip baseline di lokasi yang tercatat pada PROGRESS. Periksa jumlah tes yang lulus dan setiap pesan skip atau error pada host tersebut.

```bash
mkdir -p __pycache__
export TMPDIR="$PWD/__pycache__"
python3 -B smoke_test.py
python3 -B -m unittest discover -s tests -v
python3 -B -m experiments.security_baseline --output results/security/socket-ulangan
```

Untuk bukti paket Linux, gunakan `dumpcap` bila sudah tersedia dan akun memiliki izin capture. Pilih dua port loopback kosong, misalnya 45060 dan 45061. Di terminal pertama pada guest, mulai capture dan tunggu hingga aktif.

```bash
mkdir -p captures
dumpcap -i lo -p -f 'host 127.0.0.1 and tcp portrange 45060-45061' -s 0 -w captures/stage06-ulangan.pcapng
```

Di terminal kedua jalankan `python3 -B -m experiments.security_baseline --port 45060 --output results/security/guest-capture-ulangan`. Sesudah program berhasil, hentikan dumpcap dengan Ctrl+C. Simpan hash dengan `sha256sum captures/stage06-ulangan.pcapng`. Catat hasil analisis PCAP terpisah karena mode runner ini hanya membuat manifest endpoint. [Opsi dumpcap](https://www.wireshark.org/docs/man-pages/dumpcap.html)

## Pemeriksaan manual di Wireshark

Buka PCAP dan pilih koneksi menurut pasangan port dalam manifest. Pada PCAP Linux gunakan filter tampilan `tcp.port == 45060` untuk kontrol dan `tcp.port == 45061` untuk HPQC jika memakai contoh port di atas. Pilih paket koneksi, **Follow → TCP Stream**, lalu pilih satu arah. Pilih tampilan **Raw** dan **Save As** untuk menyimpan byte biner arah tersebut. Ulangi untuk arah sebaliknya. Cocokkan panjang dan SHA-256 tiap ekspor dengan `client` untuk arah keluar client dan `server` untuk arah keluar server pada manifest run yang sama. Cari marker ASCII pada stream hasil reassembly. Untuk memeriksa framing, baca prefix big-endian empat byte lalu maju sejumlah byte yang dinyatakan sampai akhir stream.

## Makna bagi skripsi

Kontrol plaintext menunjukkan bahwa metode observasi dapat menemukan marker ketika isinya dikirim terbuka. Pada sesi HPQC yang direkam, pengamat masih dapat melihat panjang, arah, tipe pesan dan header publik, sementara penerima memulihkan payload identik dan pengirim memverifikasi ACK. Sertakan kedua PCAP sebagai pasangan bukti. Gunakan transkrip tes untuk menunjukkan perilaku penolakan input. Cakupan kesimpulan terbatas pada implementasi, sampel, dan host ini. Pengujian formal kriptografi, sertifikasi, performa, serta pemulihan jaringan memerlukan bukti lain.
