# Stage 01 — validasi prototipe asli

Gunakan dua terminal guest milik lab dan teks sintetis di bawah. Untuk mengulang Stage 01, pulihkan source asli dari arsip ke direktori terpisah sesuai [log pengembangan](../PROGRESS.md) dan gunakan interpreter venv yang sesuai. Untuk pengujian Stage 02 pada source modular, ikuti [README](../README.md).

## 1. Identifikasi kedua guest dan jalankan smoke test

Jalankan blok berikut sekali di Ubuntu **dan** sekali di Debian. Sesuaikan `PY` dengan lokasi venv yang sudah ada. Jika import gagal, catat traceback, interpreter, dan status BLOCKED pada guest tersebut. Penyiapan atau instalasi paket merupakan tindakan tersendiri.

```bash
date -Is
cat /etc/os-release
uname -rm
ip -br -4 addr
sha256sum chat.py smoke_test.py requirements.txt README.md
PY=./.venv/bin/python
"$PY" -VV
"$PY" -c 'import sys; print(sys.executable, sys.prefix)'
"$PY" -m pip show pqcrypto cryptography psutil
"$PY" -B - <<'PYTHON'
from pqcrypto.kem.ml_kem_768 import keygen, encaps, decaps
pk, sk = keygen()
ct, client_secret = encaps(pk)
server_secret = decaps(sk, ct)
sizes = (len(pk), len(sk), len(ct), len(client_secret))
print("Ukuran dalam byte (pk, sk, ct, ss)", sizes)
assert sizes == (1184, 2400, 1088, 32), "Periksa representasi kunci/parameter library"
assert server_secret == client_secret, "Shared secret berbeda"
print("ML-KEM-768 agreement PASS")
PYTHON
echo "exit KEM=$?"
"$PY" -B smoke_test.py
echo "exit smoke=$?"
```

Cocokkan keempat hash dengan baseline. Catat bila hash berbeda, misalnya setelah konversi line ending, sebelum memakai hasil sebagai bukti untuk baseline yang sama. Jalankan dengan optimisasi Python nonaktif (variabel `PYTHONOPTIMIZE` kosong dan tanpa `-O`) karena kedua pemeriksaan memakai `assert`. Nilai 2400 byte adalah ukuran expanded decapsulation key ML-KEM-768. Simpan ukuran dan error bila library memberi representasi berbeda. [FIPS 203, Tabel 3](https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.203.pdf)

Smoke test lulus bila exit code 0 dan kedua hasil agreement/dekripsi bernilai True. Smoke test memakai satu kunci, nonce acak, serta AAD kosong (`None`). Pengujian chat berikut memeriksa jalur dua kunci, nonce dari counter, AAD arah/urutan, dan TCP.

## 2. Mulai capture sebelum membuka koneksi

Pada terminal capture **Debian**, masukkan IP aktual kedua guest pada adapter PQC-LAB. Dari `ip route get`, pilih nama interface setelah `dev`. Periksa bahwa `src` sama dengan IP Debian yang dipilih. Gunakan hanya interface dan trafik milik lab. Bila tcpdump atau hak capture tidak tersedia, catat BLOCKED untuk capture dan jalankan uji chat secara terpisah.

```bash
read -r -p 'IPv4 Ubuntu pada PQC-LAB: ' CLIENT_IP
read -r -p 'IPv4 Debian pada PQC-LAB: ' SERVER_IP
ip -4 route get "$CLIENT_IP"
read -r -p 'Nama interface lab dari hasil route: ' LAB_IF
ip -br -4 addr show dev "$LAB_IF"
tcpdump --version
mkdir -p captures
PCAP=$(mktemp captures/stage01-XXXXXXXX.pcap)
echo "$PCAP"
sudo tcpdump -p -i "$LAB_IF" -nn -s 0 -U -w - \
  "tcp port 5050 and host $CLIENT_IP and host $SERVER_IP" > "$PCAP"
```

Tunggu pesan `listening on` sebelum menjalankan client. `-p` mempertahankan mode capture non-promiscuous untuk trafik endpoint ini. File unik dibuat oleh user lokal. Filter hanya mencakup koneksi TCP/5050 antara dua IP tersebut. Capture berhenti dengan Ctrl+C sesudah sesi berakhir. Perintah ini tidak memodifikasi route, firewall, atau konfigurasi interface.

## 3. Kirim teks dalam kedua arah

Di terminal server Debian, masukkan IP Debian yang sudah diverifikasi.

```bash
read -r -p 'IPv4 Debian pada PQC-LAB: ' SERVER_IP
./.venv/bin/python -B chat.py server --host "$SERVER_IP" --port 5050
```

Di terminal client Ubuntu:

```bash
read -r -p 'IPv4 Debian pada PQC-LAB: ' SERVER_IP
./.venv/bin/python -B chat.py client --host "$SERVER_IP" --port 5050
```

1. Catat kedua fingerprint public key. Bandingkan melalui konsol VM tepercaya sebelum mengirim teks. Aplikasi hanya menampilkan fingerprint dan otomatis melanjutkan handshake.
2. Dari Ubuntu kirim `U-01`, tunggu sampai muncul sebagai `[Pesan diterima]` di Debian. Dari Debian kirim `D-01` dan lihat hasil di Ubuntu. Dari Ubuntu kirim `U-02` dan lihat hasil di Debian. Tekan Enter sekali setiap pesan.
3. Catat isi, urutan, dan terminal penerima untuk ketiga pesan. Status pengiriman lokal dan TCP ACK tidak mengonfirmasi dekripsi. Cocokkan ketiga pesan untuk menilai delivery dua arah.
4. Ketik `/quit` pada client. Catat keluaran dan apakah server masih menunggu input. Jika perlu, ketik `/quit` pada server juga. Perintah itu diproses secara lokal. Mulai ulang server untuk sesi baru.

**Varian Windows loopback.** Dengan venv yang dependency-nya sudah terverifikasi, jalankan tiga perintah berikut dari direktori proyek. Setelah smoke test, gunakan terminal pertama untuk server dan terminal kedua untuk client. Ulangi urutan pesan di atas. Catat hasil Windows terpisah dari kedua VM.

```powershell
& .\.venv\Scripts\python.exe -B .\smoke_test.py
# Terminal 1
& .\.venv\Scripts\python.exe -B .\chat.py server --host 127.0.0.1 --port 5050
# Terminal 2
& .\.venv\Scripts\python.exe -B .\chat.py client --host 127.0.0.1 --port 5050
```

## 4. Periksa hasil dengan tcpdump dan Wireshark

Di terminal capture, tekan Ctrl+C. Catat jumlah paket captured dan dropped by kernel. Di shell yang sama, periksa apakah file dapat dibaca dan ambil hash bukti:

```bash
tcpdump -nn -r "$PCAP" 'tcp port 5050'
sha256sum "$PCAP"
```

1. Buka file melalui **File → Open** di Wireshark pada mesin analisis yang memiliki akses ke salinan capture. Jika file dipindahkan, cocokkan SHA-256. Gunakan display filter `tcp.port == 5050`. Pilih koneksi yang dimulai dari Ubuntu ke Debian, catat nomor `tcp.stream`, dan periksa awal koneksi hingga penutupan.
2. Pilih **Analyze → Follow → TCP Stream**. Pilih **Hex Dump** dan periksa satu arah setiap kali. Mulai dari byte pertama stream arah tersebut. Baca prefix big-endian 4 byte sebagai panjang body, lewati sepanjang body, lalu baca prefix berikutnya. TCP dapat memecah atau menggabungkan frame aplikasi. [Wireshark User’s Guide](https://www.wireshark.org/docs/wsug_html_chunked/ChAdvFollowStreamSection.html)
3. Cocokkan dengan tabel prediksi di bawah. Body pesan mencakup ciphertext dan tag 16 byte. Nonce serta sequence dibentuk secara lokal. Ketiga teks contoh masing-masing 4 byte UTF-8, sehingga body pesan diharapkan 20 byte. Angka ini adalah prediksi dari kode dan parameter ML-KEM, belum menjadi hasil pengukuran.

| Arah stream | Urutan body pada skenario contoh | Prefix yang diharapkan (hex) |
|---|---|---|
| Debian → Ubuntu | Public key 1184 byte, lalu pesan D-01 | `00 00 04 a0`, lalu `00 00 00 14` |
| Ubuntu → Debian | KEM ciphertext 1088 byte, lalu pesan U-01 dan U-02 | `00 00 04 40`, lalu dua kali `00 00 00 14` |

4. Catat ukuran **teramati**, ID stream, hash capture, hasil di terminal penerima, dan setiap selisih. Capture yang mulai terlambat atau kehilangan byte sehingga frame tidak dapat direkonstruksi perlu diulang. Simpan raw capture di lokasi bukti privat. Pengamatan ini memvalidasi struktur wire; autentikasi identitas dan ketahanan terhadap gangguan memerlukan pengujian tersendiri.

## 5. Catat hasil

Tambahkan ke PROGRESS.md satu baris per host atau pemeriksaan: tanggal, host/guest, hash sumber, interpreter dan versi paket, command, status, hasil aktual, error, referensi bukti. Gunakan PASS hanya setelah kriteria terkait terpenuhi, FAIL untuk pemeriksaan yang dijalankan dan gagal, BLOCKED untuk prasyarat yang belum tersedia, dan NOT RUN untuk pekerjaan yang belum dijalankan.
