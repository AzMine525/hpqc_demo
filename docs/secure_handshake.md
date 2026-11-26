# Stage 04 — handshake v2

Dua endpoint lab menggunakan PSK acak 32 byte yang telah dibagikan melalui kanal tepercaya. Tujuannya adalah membuktikan kepemilikan PSK di kedua arah dan memeriksa bahwa kedua pihak menurunkan kunci dari shared secret ML-KEM yang sama. Pakai satu PSK per pasangan endpoint. Jika beberapa perangkat memakai satu PSK, masing-masing dapat membuat proof untuk kelompok tersebut.

## Urutan dan isi pesan

Client selalu memulai. Tabel berikut mendeskripsikan suite default ID 1 (ML-KEM-768, HKDF-SHA256, AES-256-GCM). Setiap frame berbentuk `uint32_be(panjang body) || versi || tipe || suite || role || payload`. Empat field sesudah prefix masing-masing satu byte. Role client adalah 0 dan server 1. Semua ukuran pada tabel adalah byte. Ukuran SERVER_HELLO dan CLIENT_KEM untuk suite lain tercantum pada [spesifikasi Stage 07](crypto_agility.md).

| Tipe dan pengirim | Isi payload, sesuai urutan wire | Panjang body | Tindakan penerima |
|---|---|---:|---|
| 1 CLIENT_HELLO, client | client_random (32) | 36 | Server membuat server_random, session ID, dan pasangan kunci KEM ephemeral baru. |
| 2 SERVER_HELLO, server | server_random (32), session ID (16), public key (1184), proof PSK server (32) | 1268 | Client memverifikasi proof terhadap transcript sebelum encapsulation. |
| 3 CLIENT_KEM, client | KEM ciphertext (1088), proof PSK client (32) | 1124 | Server memverifikasi proof sebelum decapsulation. Kedua pihak kini memiliki input derivasi empat kunci. |
| 4 CLIENT_FINISHED, client | proof dengan confirm_client (32) | 36 | Server mengonfirmasi kunci client. |
| 5 SERVER_FINISHED, server | proof dengan confirm_server (32) | 36 | Client mengonfirmasi kunci server. |

Urutan pemanggilan fungsi di tiap peran menentukan tipe yang diharapkan. Penerima memeriksa panjang **tepat** dari prefix sebelum membaca header dan payload. Header harus cocok seluruhnya. Dengan lima prefix, pertukaran ini berukuran **2520 byte** pada stream aplikasi menurut encoding, di luar overhead TCP/IP.

## Transcript, proof, dan derivasi

Misalkan `F(i, x)` adalah seluruh frame bertipe i berisi x, termasuk prefix dan header dengan role pengirimnya. Awali transcript T dengan byte ASCII `HPQC/v2/handshake` diikuti satu byte nol. Untuk CLIENT_HELLO, tambahkan frame utuh ke T. Untuk masing-masing pesan berikutnya:

1. Ambil x sebagai konten sebelum proof. Pada kedua pesan Finished, x kosong.
2. Hitung D = SHA-256(T || F(i, x)). Prefix pada F(i, x) memuat panjang header dan x. Ini menghindari ketergantungan melingkar pada proof yang sedang dihitung.
3. Hitung proof = HMAC-SHA256(K, ASCII(`HPQC/v2/proof`) || byte nol || D). Untuk pesan 2 dan 3, K adalah PSK. Untuk pesan 4 dan 5, K adalah kunci konfirmasi khusus peran. Tipe dan role di dalam F membedakan tujuan proof serta arah penggunaannya.
4. Pengirim menambahkan F(i, x || proof) ke T setelah pengiriman. Penerima membandingkan proof 32 byte dengan `hmac.compare_digest` dan hanya menambahkan frame setelah verifikasi berhasil.

Kedua pihak memanggil `derive_keys` dari Stage 03 dengan shared secret, kedua random, versi, suite, dan SHA-256(T) tepat setelah pesan 3. Nilai tersebut mengikat kedua proof PSK, public key, session ID, serta KEM ciphertext. SERVER_FINISHED juga mengikat frame CLIENT_FINISHED yang telah diverifikasi server. Hash publik pada sesi adalah SHA-256(T) setelah pesan 5. [Kontrak Crypto Engine](crypto_engine.md)

ML-KEM dapat menghasilkan dua secret berbeda ketika ciphertext sepanjang 1088 byte mengalami perubahan. Proof PSK dan proof Finished menguji dua hal yang berbeda. Uji Stage 04 mempertahankan transcript wire dan PSK yang cocok, lalu memberikan ciphertext berbeda dengan panjang yang benar pada decapsulation lokal. Server menolak CLIENT_FINISHED. Konfirmasi bilateral dengan kunci terpisah dibahas dalam [NIST SP 800-227 §4.4](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-227.pdf).

## API sesi dan timeout

`protocol.handshake_v2.establish(sock, *, role, psk, timeout=10.0, suite="ml-kem-768")` mengambil kepemilikan satu socket yang sudah terhubung. Caller memakai role `"client"` atau `"server"`, PSK bertipe bytes, dan timeout positif dalam detik. Sediakan socket eksklusif selama handshake. Pada sukses, `ConfirmedSession.suite_id` memuat ID wire untuk pembentukan konteks DATA/ACK.

- Satu deadline monotonic berlaku untuk kelima pesan. Sebelum setiap pembacaan parsial dan pengiriman, socket memakai sisa waktu. Deadline diperiksa kembali sebelum sesi diberikan. Batas ini mencakup waktu komputasi lokal dalam keputusan akhir. Panggilan native KEM yang sedang berjalan selesai dahulu. Waktu menunggu `accept()` dan membuat koneksi TCP berada di luar handshake.
- Pada sukses, timeout socket sebelumnya dipulihkan. Hasil `ConfirmedSession` berisi role numerik, session ID, hash transcript akhir, dan `traffic_keys.send/receive` sesuai arah lokal. PSK dan kunci konfirmasi tidak menjadi field sesi. Gunakan `with establish(...) as session` atau panggil `close()` saat selesai. Penutupan bersifat idempoten, menutup socket dan melepas referensi kunci milik sesi. Python tidak menjamin zeroization atau pencabutan salinan yang telah diambil caller.
- Bila input lokal keliru, API menutup socket dan memberi `ValueError`. Kegagalan handshake menutup socket tanpa mengembalikan sesi. `HandshakeTimeout` membedakan kedaluwarsa dari `HandshakeError` lain seperti proof salah, versi/suite tidak cocok, frame terpotong, atau urutan salah.
- Server dapat menyatakan sukses lokal setelah memverifikasi CLIENT_FINISHED dan mengirim SERVER_FINISHED. Client baru dapat menyatakan sukses setelah memverifikasi pesan terakhir itu. Bila pesan terakhir rusak atau hilang, server tidak memperoleh bukti bahwa client telah menerimanya. Batas ini juga berlaku pada interpretasi hasil eksperimen.

## Menjalankan di Windows, Ubuntu, atau Debian

Dari root proyek gunakan interpreter venv yang memiliki dependency proyek. Contoh memakai nama `python` dari venv aktif. Untuk satu uji loopback, buat PSK sekali di direktori kerja privat dengan perintah berikut. Mode exclusive mencegah penimpaan file lama. Pada Windows, gunakan direktori yang ACL-nya hanya memberi akses kepada pengguna lab. Untuk dua perangkat, sediakan salinan biner identik melalui kanal provisioning tepercaya.

```text
python -c "import os,secrets; fd=os.open('stage04.psk',os.O_CREAT|os.O_EXCL|os.O_WRONLY|getattr(os,'O_BINARY',0),0o600); f=os.fdopen(fd,'wb'); f.write(secrets.token_bytes(32)); f.close()"
```

Jalankan server di terminal pertama, lalu client di terminal kedua. Untuk uji antar-VM, gunakan alamat adapter lab Debian sebagai `--host` pada kedua proses.

```text
python -B -m protocol.handshake_cli server --host 127.0.0.1 --port 5050 --psk-file stage04.psk
python -B -m protocol.handshake_cli client --host 127.0.0.1 --port 5050 --psk-file stage04.psk
```

Pada sukses, masing-masing CLI menampilkan session ID publik yang sama dan menutup sesi. Opsi `--timeout` mengatur deadline handshake dalam detik. Kegagalan menghasilkan exit code nonzero. CLI ini hanya menjalankan handshake. Chat lama tetap tersedia melalui `chat.py`.

```text
python -B -m unittest discover -s tests -p test_handshake_v2.py -v
python -B -m unittest discover -s tests -v
python -B smoke_test.py
```

Tes handshake mencakup dua proses CLI di TCP loopback, verifikasi empat proof dan derivasi menggunakan encoding referensi di tes, gangguan pada konten/proof melalui fixture lokal, serta pembacaan parsial dengan jam terkontrol. Tes interoperabilitas Stage 02 memakai arsip asli yang dijelaskan di [README](../README.md). Protokol ini merupakan prototipe penelitian dan belum diaudit secara formal.
