# Stage 07 — Pemilihan suite HPQC v2

Kedua endpoint menetapkan satu suite secara lokal sebelum koneksi diproses. ID satu byte yang sudah ada pada v2 mengidentifikasi pilihan tersebut. Jika opsi dihilangkan, endpoint memakai ML-KEM-768 (ID 1). Server membandingkan ID pada CLIENT_HELLO dengan konfigurasi lokal sebelum membuat keypair. Jika berbeda, server menutup socket dan client juga gagal. Tidak ada negosiasi, percobaan ulang dengan suite lain, atau downgrade otomatis.

## Identitas dan ukuran wire

Semua ukuran dalam byte. Kolom SERVER_HELLO dan CLIENT_KEM adalah ukuran body termasuk header 4 byte. Kolom total meliputi prefix 4 byte pada masing-masing dari lima frame dan mengecualikan TCP/IP.

| Opsi `--suite` | ID | Public key | Ciphertext pembentukan secret | SERVER_HELLO | CLIENT_KEM | Total handshake |
|---|---:|---:|---:|---:|---:|---:|
| `ml-kem-768` | 1 | 1184 | 1088 | 1268 | 1124 | 2520 |
| `ml-kem-512` | 2 | 800 | 768 | 884 | 804 | 1816 |
| `ml-kem-1024` | 3 | 1568 | 1568 | 1652 | 1604 | 3384 |
| `rsa-2048-oaep` | 4 | 294 | 256 | 378 | 292 | 798 |

ID 2–4 merupakan alokasi proyek. Semua suite menghasilkan secret 32 byte. Tiga ukuran body lain adalah 36 byte masing-masing. Angka tersebut berasal dari encoding dan diperiksa oleh tes frame untuk keempat suite.

## Kontrak pembentukan secret

Registry memetakan nama CLI ke ID wire dan objek `KeyEstablishment`. `public_size` dan `ciphertext_size` menentukan panjang yang diterima parser. Private key hanya dimiliki server selama handshake. [Registry dan implementasi RSA](../crypto_engine/v2/suites.py) · [Adaptor ML-KEM](../crypto_engine/v2/kem.py)

| Operasi | Kontrak |
|---|---|
| `generate_keypair()` | Menghasilkan pasangan ephemeral baru berupa public key wire dan private key lokal. ML-KEM menggunakan expanded private key 1632/2400/3168 byte untuk 512/768/1024. RSA menyimpan objek private key milik library dalam memori. |
| `encapsulate(public)` | Memvalidasi public key lalu mengembalikan `(ciphertext, secret)`. ML-KEM menggunakan `pqcrypto`. RSA memeriksa public key RSA-2048 kanonis dalam format DER SubjectPublicKeyInfo, eksponen 65537, lalu mengenkripsi 32 byte baru dari CSPRNG dengan OAEP SHA-256, MGF1-SHA256, dan label kosong. |
| `decapsulate(private, ciphertext)` | Mengembalikan secret 32 byte. Kesalahan input atau OAEP ditolak. ML-KEM dapat menghasilkan secret berbeda untuk ciphertext panjang-valid melalui implicit rejection. Kedua peran memeriksa Finished sebelum membuka channel. |

## Alur handshake dan DATA/ACK

1. Client mengirim CLIENT_HELLO dengan ID lokal. Server memeriksa panjang dan header yang diharapkan, membuat keypair ephemeral, lalu mengirim public key dan proof PSK pada SERVER_HELLO.
2. Client memeriksa proof dan memakai backend suite lokal untuk membentuk secret. Server memeriksa proof CLIENT_KEM sebelum membuka ciphertext. Kelima header, termasuk ID suite, terikat pada transcript. Kedua pihak memasukkan ID yang sama ke HKDF-SHA256 dan memakai kunci konfirmasi terpisah untuk dua pesan Finished. [Spesifikasi handshake](secure_handshake.md)
3. `DataChannel(sock, *, role, psk, timeout=10.0, suite="ml-kem-768")` membentuk konteks AES-256-GCM per arah dari sesi terkonfirmasi. ID suite ikut dalam AAD pada setiap DATA dan ACK. Validasi sesi, arah, urutan, nonce, tag, ID pesan dan ukuran payload mengikuti protokol transfer. [Format record dan perilaku penerima](secure_data.md)

## Menjalankan dan menguji

Gunakan root proyek dan interpreter dengan dependency proyek. Perintah berlaku untuk Windows, Ubuntu, dan Debian. Pada Linux dapat memakai `python3`; pada Windows pilih executable venv atau interpreter pada [catatan environment pengujian](security_testing.md). Siapkan satu PSK biner 32 byte untuk kedua proses sesuai [panduan provisioning lab](secure_handshake.md). Contoh berikut memakai file `stage04.psk`.

Mulai server di terminal pertama.

```text
python -B -m protocol.transfer_cli server --host 127.0.0.1 --port 5050 --psk-file stage04.psk --suite rsa-2048-oaep --text "balasan server"
```

Jalankan client di terminal kedua.

```text
python -B -m protocol.transfer_cli client --host 127.0.0.1 --port 5050 --psk-file stage04.psk --suite rsa-2048-oaep --text "pesan client"
```

Ganti nama suite pada kedua terminal untuk memilih varian ML-KEM. Untuk handshake saja, gunakan `protocol.handshake_cli` dengan argumen yang sama kecuali `--text`. Pada transfer sukses, tiap terminal melaporkan DATA diterima dan ACK terverifikasi. Untuk mengulang kasus mismatch, mulai dua proses baru dan pilih dua suite berbeda. Keduanya harus keluar nonzero sebelum delivery.

```text
python -B -m unittest discover -s tests -p test_agility.py -v
python -B -m unittest discover -s tests -v
python -B smoke_test.py
```

Full regression menggunakan arsip prototipe untuk dua tes chat legacy. Lokasi atau variabel `HPQC_BASELINE_ZIP` dijelaskan dalam [README](../README.md).

## Hasil dan interpretasi penelitian

Pada Windows loopback, keempat suite lulus agreement, pemeriksaan ID dalam transcript/KDF dan record DATA/ACK, delivery dua arah serta penolakan replay. Seluruh 12 kombinasi mismatch terurut ditolak pada hello pertama. CLI mengirim file 1 MiB dan balasan UTF-8 pada setiap suite. Dengan ID 1, client baru berfungsi dengan server dari commit acuan dan sebaliknya. Suite RSA berperan sebagai pembanding klasik dengan jalur payload, aturan autentikasi PSK dan delivery yang sama. Hasil ini mendukung perbandingan implementasi. Kesetaraan tingkat keamanan, performa relatif, serta perilaku pada VM memerlukan bukti tersendiri. [Transkrip 69 tes](../results/stage07/test-results.txt) · [Catatan eksekusi dan identitas source](../PROGRESS.md)
