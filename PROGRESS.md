# Log pengembangan dan verifikasi HPQC

## 26 November 2026 — Stage 09, pemulihan pengiriman

**Implementasi dan uji Windows loopback PASS. Penerimaan keseluruhan Stage 09 masih parsial.** Matriks impairment Linux, pemeriksaan rute pengelolaan secara langsung, serta rollback qdisc nyata pada guest berstatus **NOT RUN**. Pemeriksaan XML VirtualBox baca-saja menemukan hanya slot 0 aktif pada masing-masing Ubuntu-PQC dan Debian-PQC, keduanya NATNetwork PQC-LAB. Status akses konsol dan rute SSH aktif memerlukan pemeriksaan operator sebelum menjalankan panduan dengan izin eksplisit.

Pada preflight, `git --no-optional-locks status`, `git rev-parse HEAD` dan pembacaan manifest menunjukkan branch `step07` pada `6da416e3c52995b066e465384af4f11ad7751449` dengan perubahan Stage 08 di working tree. Hash source pada manifest Stage 08, ketiga CSV, transkrip dan arsip prototipe cocok dengan bukti sebelumnya. Stage 08 telah memenuhi kriteria lokal dengan 368/368 percobaan dan regresi 74/74. Source dan bukti Stage 08 dipertahankan saat Stage 09 ditambahkan.

Perubahan mencakup CLI dan lapisan aplikasi di `protocol/resilience_cli.py` serta `protocol/resilience.py`, klasifikasi error transport handshake di `protocol/handshake_v2.py`, dan akses ID sesi publik di `protocol/data_v2.py`. Setiap reconnect menjalankan handshake baru dengan PSK dan suite yang sama. ID pesan aplikasi tetap sepanjang retry. Inbox SQLite melakukan commit sebelum mengirim receipt dan memeriksa kesamaan payload saat menerima ID yang pernah diproses. Benchmark ada di `benchmark/bench_resilience.py` dan tes ada di `tests/test_resilience.py`. [Format, alur operasi dan panduan tc netem](docs/resilience.md)

| Pemeriksaan aktual | Hasil |
|---|---|
| `python -B -m protocol.resilience_cli --help`, `python -B -m benchmark.bench_resilience --help`, `python -B smoke_test.py` | Exit 0. CLI tersedia. Agreement serta dekripsi baseline berhasil. |
| `python -B -m unittest discover -s tests -p test_resilience.py -v` | **6/6 PASS**. Uji kehilangan receipt, sesi baru, heartbeat terjadwal, timeout peer diam, PSK salah, retry/backoff terbatas, ID keliru dengan payload berbeda, database dibuka kembali, dan dua proses CLI menggunakan ML-KEM-512. |
| `python -B -m benchmark.bench_resilience --output results/stage09/loopback.json` | Exit 0. Pada 20.18 WIB, host Windows build 26300, CPython 3.11.9, pqcrypto 1.0.0, cryptography 49.0.0. Mode normal ML-KEM-768 mengonfirmasi 3/3 pesan, 3 baris inbox, nol duplikat. Outage layanan 200 ms mengonfirmasi 3/3 pesan, 3 baris, 1 kiriman ulang dikenali, serta 0 receipt selama dan 2 sesudah outage. [Event, kebijakan skenario dalam source teridentifikasi, dan metrik mentah](results/stage09/loopback.json) |
| Penghitungan dari jam monotonic client | Sesudah deteksi pertama, TCP tersambung pada 41,514 ms. Koneksi yang kemudian menyelesaikan handshake tersambung pada 266,167 ms. Sesi aman siap pada 270,239 ms dan receipt pesan diperoleh pada 272,833 ms. Tiga interupsi transport dalam sembilan percobaan DATA/heartbeat, nol timeout pada run outage. |
| `python -B -m unittest discover -s tests -v` | **80/80 PASS**, 19,431 detik, tanpa skip. [Transkrip lengkap](results/stage09/test-results.txt) |
| Blok Bash dari panduan, `bash --noprofile --norc -n` dan eksekusi dengan fungsi pengganti untuk `ip`, `tc`, `sleep` | Sintaks PASS. Pada simulasi, 9/9 profil melewati pemasangan dan rollback, 5/5 kondisi penolakan berhenti sebelum perubahan (rute bersama, peer SSH keliru, gagal membaca class atau filter, nama profil keliru). Rollback qdisc dalam kernel Linux masih NOT RUN. |
| `python -B -` dengan `compile`, `hashlib` dan pemeriksaan tautan lokal, lalu `git diff --check` | PASS. SHA-256 event JSON `819460c00b1f1d7ab9fd620505805416f9fec4a77af1269824b04351e223a93f` dan transkrip `b929cd9a6f90d301b5ed5b3b7fe057b119bcf7d33a1db9ffa3f6fe44d2e4d9d6`. Lima hash source pada JSON cocok. |

Eksperimen memutus layanan aplikasi sesudah transaksi inbox selesai sambil mempertahankan listener TCP. Hasilnya mendukung analisis recovery aplikasi dan deduplikasi. Klaim loss, jitter, retransmisi dan recovery guest memerlukan pengukuran Linux sesuai matriks pada panduan. Pemeriksaan dan perubahan dibatasi sampai Stage 09.

## 26 November 2026 — Stage 08, benchmark otomatis

**Status akhir. Kriteria Stage 08 lulus pada Windows TCP loopback.** Preflight baca-saja menemukan branch `step07` bersih pada `6da416e3c52995b066e465384af4f11ad7751449`. SHA-256 transkrip Stage 07 cocok dan memuat 69 hasil OK. Enam tes `test_agility.py` lulus ulang, termasuk agreement, DATA/ACK, replay, PSK salah dan seluruh kombinasi suite berbeda. Tes CLI dan uji silang ID 1 tercatat dalam bukti Stage 07. SHA-256 arsip prototipe dan kedua PCAP Stage 06 cocok dengan catatan sebelumnya.

Benchmark ditambahkan pada `benchmark/workloads.py` dan `benchmark/run_experiment.py`. Runner memakai engine dan channel produksi dengan PSK, payload dan material sesi sintetis dalam memori. Pengukuran lokal dan TCP dikumpulkan per suite. Durasi wall memakai `perf_counter_ns()`, CPU proses memakai `process_time_ns()`, dan RSS berasal dari snapshot psutil awal/akhir. Network trial memakai satu sesi baru per ukuran dengan satu DATA/ACK dari setiap arah. [Metode sampling, definisi metrik, batas interpretasi dan panduan lintas platform](docs/benchmark.md)

| Command atau pemeriksaan aktual | Hasil |
|---|---|
| `python -B -m unittest discover -s tests -p test_agility.py -v` | PASS 6/6 saat preflight, sebelum source diedit. |
| `python -B -m unittest discover -s tests -p test_benchmark.py -v` | PASS 5/5 saat integrasi. Mencakup agregasi, data kosong, ACK/payload salah, kegagalan handshake, TCP_INFO dengan fixture, dan CSV dari transfer loopback nyata. |
| `python -B -m benchmark.run_experiment --help` dan `python -B smoke_test.py` | Keduanya exit 0. CLI menampilkan opsi pemilihan suite serta mode. Smoke test mengonfirmasi agreement ML-KEM dan dekripsi AES-GCM. |
| `python -B -m benchmark.run_experiment --output results/stage08/windows-loopback-01 --warmup 3 --trials 20` | Exit 0 dengan 368 percobaan tanpa kegagalan workload. Pemeriksaan CSV menemukan baris status `trial` ikut menghasilkan grup statistik kosong. Agregator diperbaiki dan assertion ditambahkan. Artefak awal dipindahkan ke cache workspace `__pycache__/stage08-initial-run/`. |
| `python -B -m unittest discover -s tests -v` | Regresi final **74/74 PASS** tanpa skip, 8,949 detik. [Transkrip](results/stage08/test-results.txt) |
| `python -B -m benchmark.run_experiment --output results/stage08/windows-loopback-02 --warmup 3 --trials 20` | Exit 0. **368/368** percobaan workload sukses, terdiri dari 48 warm-up dan 320 terukur. Fase terukur mencakup 80 trial kriptografi lokal dan 240 sesi TCP. **480/480** DATA/ACK terukur terverifikasi, ditambah 72/72 pada warm-up. [Manifest](results/stage08/windows-loopback-02/manifest.json) |
| `python -B -` memakai `csv`, `statistics`, `hashlib`, dan `compile`, serta `git diff --check` | PASS setelah perbaikan. Hitung ulang 340 grup dari 8.188 baris raw, verifikasi 20 trial per grup, semua ukuran handshake, hash source dan statistik. File Python benchmark lolos kompilasi. |

Run final dimulai sekitar 20.01 WIB pada host Windows build 26300 dengan CPython 3.11.9, pqcrypto 1.0.0, cryptography 49.0.0 dan psutil 7.2.2. Manifest mencatat identitas host, versi, argumen aktual dan SHA-256 source. Pada payload 100 KiB, contoh median terukur dari 20 trial per suite ditampilkan di bawah. Goodput dan RTT mengacu pada client ke server.

| Suite | Keygen lokal (ms) | Handshake (ms) | Handshake (byte) | RTT (ms) | Goodput (MiB/s) |
|---|---:|---:|---:|---:|---:|
| ML-KEM-768 | 0,395 | 4,588 | 2.520 | 1,303 | 74,94 |
| ML-KEM-512 | 0,264 | 4,087 | 1.816 | 1,372 | 71,17 |
| ML-KEM-1024 | 0,605 | 5,469 | 3.384 | 1,415 | 69,02 |
| RSA-2048-OAEP | 191,420 | 209,453 | 798 | 1,477 | 66,14 |

[Raw kriptografi](results/stage08/windows-loopback-02/crypto_raw.csv) · [Raw komunikasi](results/stage08/windows-loopback-02/network_raw.csv) · [Mean, median, SD, dan p95](results/stage08/windows-loopback-02/summary.csv)

Retransmisi Windows berstatus `unavailable` untuk semua 480 observasi terukur. Pembacaan Linux TCP_INFO diperiksa dengan fixture. Eksekusi di Ubuntu dan Debian **NOT RUN**. Hasil menggambarkan loopback pada satu host, CPU gabungan kedua peran, dan RSS pada batas operasi. Dataset memungkinkan perhitungan ulang biaya pembentukan secret, biaya wire, dan metrik delivery DATA/ACK untuk skripsi. Validasi pengguna diperlukan sebelum Stage 09.

## 26 November 2026 — Stage 07, crypto-agility

**Checkpoint sebelum implementasi.** Pada `main` di `f181af3aff2b8c0a1412b43c72dec9e67d652183`, pemeriksaan `git status`, `git diff`, file baru dan source menemukan pekerjaan Stage 06 di working tree serta konstanta suite 1 di protokol. Proses sebelumnya berhenti sesudah preflight dan probe API, sebelum implementasi Stage 07 atau koreksi dokumentasi. ZIP baseline cocok dengan hash tercatat. Lima tes bukti Stage 06 lulus saat preflight. Transkrip 63 tes, tiga file alat/tes dan kedua PCAP tersedia. `Get-FileHash` mengonfirmasi hash PCAP dan hash asli transkrip. Dua digit yang terlewat saat menyalin hash transkrip diperbaiki di [laporan Stage 06](docs/security_testing.md).

Probe Windows memakai CPython 3.11.9, pqcrypto 1.0.0 dan cryptography 49.0.0. Ketiga modul ML-KEM menyediakan `keygen()`, `encaps(pk_bytes)`, `decaps(sk_bytes, ct_bytes)`. Ukuran public/private/ciphertext/secret terukur 800/1632/768/32, 1184/2400/1088/32 dan 1568/3168/1568/32 byte. Probe RSA-2048 OAEP-SHA256 menghasilkan public key DER-SPKI 294 byte, ciphertext 256 byte, dan dekripsi secret acak 32 byte yang cocok. Akses dokumentasi web mengembalikan HTTP 401. Seluruh backend dapat dipakai lokal.

**Status akhir. Seluruh kriteria penerimaan Stage 07 lulus di Windows lokal.** Default ID 1 melayani endpoint ML-KEM-768 terdahulu. ID baru 2/3/4 mewakili ML-KEM-512, ML-KEM-1024 dan RSA-2048-OAEP. Pilihan suite ditetapkan di setiap endpoint. Eksperimen memakai akun dan dependency Windows yang sudah tersedia, dengan direktori temporer proses tes di `__pycache__` dalam workspace. [Kontrak API, ukuran frame dan prosedur CLI](docs/crypto_agility.md)

| Command atau pemeriksaan aktual | Hasil Windows |
|---|---|
| `python -B -m protocol.handshake_cli --help` dan `python -B -m protocol.transfer_cli --help` | Keduanya exit 0 dan menampilkan keempat pilihan serta default ML-KEM-768. |
| `python -B -m unittest discover -s tests -p test_agility.py -v` saat integrasi | Versi awal 5/5 PASS. Pemeriksaan PSK salah untuk seluruh suite ditambahkan sesudahnya dan lulus dalam regresi final. |
| `python -B -m unittest discover -s tests -v` setelah implementasi | **69/69 PASS**, tanpa skip, dalam 9,097 detik. Mencakup 6 tes Stage 07 dengan subtes per suite. Empat backend menghasilkan secret cocok 32 byte. Keempat suite lulus verifikasi ukuran wire, konteks HKDF, DATA/ACK dua arah dan penolakan replay serta PSK salah. Dua belas mismatch terurut menutup kedua socket sebelum keygen, dengan satu CLIENT_HELLO dan nol frame balasan. CLI mentransfer file 1 MiB serta balasan UTF-8 per suite. [Transkrip lengkap](results/stage07/test-results.txt) |
| `git archive --format=zip f181af3aff2b8c0a1412b43c72dec9e67d652183 config.py protocol crypto_engine`, lalu `python -B -` dengan dua proses `python -B -m protocol.transfer_cli` | PASS 3/3 skenario TCP loopback. Source acuan dibaca ke direktori temporer di workspace. Client baru dengan pilihan eksplisit ID 1 ke server acuan dan client acuan ke server baru default menghasilkan exit 0 pada kedua peran, isi file cocok dua arah serta ACK terverifikasi. Client baru ML-KEM-512 ke server baru RSA menghasilkan exit 1 pada kedua peran dan kedua file tujuan tidak terbentuk. |
| `python -B smoke_test.py` | Exit 0, agreement ML-KEM dan dekripsi AES-256-GCM berhasil. |
| `python -B -` dengan `compile` dan `hashlib` | Sintaks sembilan file implementasi dan tes Stage 07 lulus. Sesudah koreksi dokumentasi, keenam hash pada tabel bukti Stage 06 cocok dengan file aslinya. Kedua PCAP serta transkrip lama tetap berada di lokasi semula. |

Identitas revisi kerja Stage 07 adalah SHA-256 `09f276616a9cbcca60f17e9fd079143205b930c4132e4eca5e385ec49436f447` atas konkatenasi digest SHA-256 biner sembilan file dalam urutan berikut: `crypto_engine/v2/kem.py`, `crypto_engine/v2/suites.py`, `protocol/data_v2.py`, `protocol/handshake_cli.py`, `protocol/handshake_v2.py`, `protocol/transfer_cli.py`, `tests/test_agility.py`, `tests/test_data_v2.py`, `tests/test_handshake_v2.py`. SHA-256 transkrip Stage 07 adalah `0ad4ba8a8f34d78def71760b564787d522e78b2b71c84b234e4389d93c52f81c`.

Ubuntu dan Debian **NOT RUN**. Untuk skripsi, data ini membuktikan agreement dan delivery bagi empat pilihan pada host pengujian. Pengukuran komparatif performa berada di Stage 08 dan menunggu validasi pengguna.

## 26 November 2026 — Stage 06, pengujian keamanan

**Seluruh kriteria Stage 06 lulus pada Windows loopback.** Git berada pada `main` di `f181af3aff2b8c0a1412b43c72dec9e67d652183`. Preflight baca-saja menemukan working tree bersih. Hash gabungan empat file Stage 05 cocok dengan `36a684a4614d1720359bb5e292aec984130040ec8262bcf4bfa6c6bf0e5443af`. SHA-256 ZIP prototipe cocok dengan `4c96cd9f4462b5b1a1f1350c4b1fd4ea572c80343f76997b41625e19b381a981`. Sebanyak 12 tes Stage 05 yang tidak membuat file lulus sebelum pengeditan. Tes CLI dengan file temporer sudah memiliki bukti PASS pada entri Stage 05 dan lulus kembali dalam suite lengkap di bawah.

Pengujian memakai CPython 3.11.9, pqcrypto 1.0.0, cryptography 49.0.0, dan dependency yang telah tersedia dari Stage 02. `python` pada tabel merujuk ke executable 3.11.9 di inventaris Windows. File temporer suite ditempatkan di cache workspace. Uji negatif memakai fixture lokal. PCAP merekam dua koneksi positif yang hanya memakai data sintetis dan port milik runner. [Metode, perintah per platform, hash dan matriks penerimaan](docs/security_testing.md)

| Command atau pemeriksaan aktual | Hasil |
|---|---|
| `git status`, hash file/arsip dan `python -B -` dengan `unittest.TestSuite` atas `DataTests` selain tes CLI temporer | PASS 12/12 pada preflight. Pemeriksaan mencakup delivery dua arah hingga 1 MiB, bentuk wire, ACK, serta penolakan perubahan dan replay. |
| Probe command capture dan driver, `sc.exe query npcap`, `sc.exe query npf`, `pktmon status` | dumpcap, tshark dan tcpdump tidak ditemukan pada host. Kedua kueri driver mengembalikan error 1060. Kueri status PktMon dari sandbox mendapat Access denied; pemeriksaan berizin melaporkan Packet Monitor tidak berjalan. Capture menggunakan socket IPv4 loopback Windows. |
| `python -B -m experiments.security_baseline --windows-capture --output results/security/capture-01` | PASS. Pukul 15.49 WIB, plaintext 9 paket (file 2.608 byte), HPQC 25 paket (file 6.336 byte). Keempat stream arah cocok byte demi byte dengan data endpoint. Kedua payload 1 KiB tiba pada kedua mode. Kedua ACK HPQC cocok dengan ID pengirim. [Manifest capture](results/security/capture-01/summary.json) |
| `python -B -m experiments.security_baseline --output results/security/socket-01` | PASS. Pengulangan tanpa akses capture memeriksa framing, delivery, ACK dan marker. [Manifest endpoint](results/security/socket-01/summary.json) |
| `python -B smoke_test.py` | PASS. Agreement ML-KEM dan dekripsi AES-GCM berhasil. |
| `python -B -m unittest discover -s tests -p test_security_evidence.py -v` | PASS 5/5. DATA lama setelah tiga delivery, tag ACK rusak, payload kontrol identik dan dua tes integritas reassembly. |
| `python -B -m unittest discover -s tests -v` | PASS 63/63 dalam 3,812 detik, tanpa skip. Mencakup engine, handshake, transfer, interoperabilitas chat dan bukti Stage 06. [Transkrip lengkap](results/security/test-results.txt) |
| `python -B -` dengan `compile`, `struct`, `hashlib` dan reassembly; `git diff --exit-code HEAD -- chat.py client.py server.py protocol crypto_engine requirements.txt` | PASS. Tiga file Python baru lolos sintaks. Kedua PCAP memiliki header versi 2.4, LINKTYPE_RAW, panjang paket lengkap. Keempat panjang, hash dan hitungan marker stream cocok dengan manifest. Diff aplikasi kosong. |

Keputusan penelitian menggunakan kontrol dengan satu frame per arah dan payload identik agar keterlihatan marker dapat dibandingkan. Pada stream plaintext marker pengirim muncul sekali per arah. Pada HPQC kedua marker muncul nol kali dalam 4.888 byte stream gabungan. Kasus stale mempertahankan sequence penerima di 3 dan jumlah ACK di 3. Kasus tag ACK rusak mempertahankan status pengiriman belum terkonfirmasi. Keduanya menutup sesi.

Ubuntu dan Debian **NOT RUN**. PCAP mentah diabaikan Git dan tersedia di workspace ini. Analisis Wireshark manual belum dijalankan. Hasil hanya berlaku untuk skenario lokal dan data sintetis yang tercantum. Stage 07 menunggu validasi pengguna.

## 26 November 2026 — Stage 05, secure data transmission

**Status: acceptance criteria Stage 05 lulus pada Windows lokal.** Pada preflight baca-saja, hash tiga file Stage 04 cocok dengan `adeae3f5…63f5cf`, dan SHA-256 ZIP baseline cocok dengan log. Dari suite Stage 04, 12 tes berbasis socket lokal dijalankan dengan `python -B -` dan `unittest.TestSuite` sebelum source diedit (12 PASS). Tes CLI ke-13 membuat PSK temporer, sehingga diuji ulang bersama regresi lengkap setelah preflight. Log Stage 04 sebelumnya mencatat 13/13 PASS.

Host memakai CPython 3.11.9, pqcrypto 1.0.0 dan cryptography 49.0.0. PYTHONPATH memakai dependency Stage 02 yang sudah ada. TMPDIR, TMP, dan TEMP bagi proses pengujian menunjuk direktori cache di workspace. SHA-256 gabungan source Stage 05 adalah `36a684a4614d1720359bb5e292aec984130040ec8262bcf4bfa6c6bf0e5443af` (SHA-256 atas gabungan digest SHA-256 biner protocol/data_v2.py, protocol/transfer_cli.py, protocol/handshake_cli.py, lalu tests/test_data_v2.py).

| Command/pemeriksaan aktual | Hasil |
|---|---|
| `python -B -m unittest discover -s tests -p test_data_v2.py -v` | PASS 13/13. Byte header, prefix, tag, overhead, batas frame, fragmentasi, dan ACK terverifikasi. Data biner 1 KiB, 100 KiB, 1 MiB dikirim serentak kedua arah. CLI TCP loopback mengirim file 1 MiB dan membalas teks UTF-8. Isi kedua file keluaran cocok. |
| Tes negatif dalam suite Stage 05 | PASS. Record dengan versi, suite, sesi, arah, tipe, sequence, nonce, panjang, ciphertext atau tag yang salah ditolak. Replay dalam/lintas sesi, ID/nonce berulang dengan tag valid, ACK yang tidak diminta/keliru/duplikat, serta body terpotong atau oversized diuji. Sequence penerima dan jumlah ACK diperiksa pada penolakan. Wrong PSK menggagalkan pembentukan channel. |
| `python -B -m unittest discover -s tests -v` dan pemeriksaan final dengan opsi `-q` | PASS 58/58 tanpa skip pada kedua run. Termasuk kelima pesan handshake, CLI Stage 04, Crypto Engine dan tiga kombinasi chat baseline. |
| Pengulangan `DataTests.test_simultaneous_bidirectional_binary_sizes` sepuluh kali menggunakan unittest pada `python -B -` | PASS 10/10. Pada run awal sebelum koreksi, satu assertion harness mengasumsikan DATA selalu mendahului ACK masuk. Keduanya memiliki urutan relatif yang sah saat pengiriman simultan. Harness kini memeriksa kedua event, ID, payload, dan sequence wire. |
| `python -B smoke_test.py` dan `python -B -m protocol.transfer_cli --help` | PASS. Agreement serta dekripsi baseline berhasil dan CLI transfer tersedia. |

Keputusan implementasi: handshake Stage 04 dan cipher Stage 03 dipakai langsung. DATA/ACK berbagi satu counter per arah. Message ID 16 byte ditempatkan di plaintext terenkripsi. Satu pesan per arah dapat menunggu ACK. Header 44 byte, prefix 4 byte, dan tag 16 byte memberi overhead tetap 64 byte. ID menambah 16 byte lagi. Parser dan pembukaan endpoint CLI dipakai bersama dengan CLI handshake. [Spesifikasi, diagram, panduan menjalankan dan menguji](docs/secure_data.md)

Untuk skripsi, delivery dapat dihitung dari ACK terautentikasi yang cocok dengan ID pesan. ACK mendahului penulisan file dan membuktikan pemrosesan di memori pada peer yang menjalankan implementasi ini. Hasil Windows belum mengukur performa, packet loss, atau pemulihan. Stage 05 pada Ubuntu/Debian berstatus NOT RUN. Stage 06 menunggu persetujuan pengguna.

## 26 November 2026 — Stage 04, secure handshake

**Status: seluruh acceptance criteria Stage 04 lulus secara lokal pada Windows.** Preflight baca-saja dilakukan sebelum source diubah. Kriteria engine Stage 03 lulus 18/18, smoke test exit 0 dan hash gabungan source Stage 03 cocok dengan entri sebelumnya. SHA-256 ZIP baseline juga cocok. Git lokal masih berada di master tanpa commit.

Lingkungan uji: CPython 3.11.9, pqcrypto 1.0.0, cryptography 49.0.0, memakai PYTHONPATH ke dependency sementara Stage 02 yang sudah tersedia. Untuk eksekusi suite baru dan regresi, TMPDIR/TMP/TEMP milik proses uji diarahkan ke direktori cache di workspace. Identitas source Stage 04 adalah `adeae3f5a3b9fc09dcc484165173dc2dfddee4de2dc5dd02077a93198363f5cf` (SHA-256 atas gabungan digest SHA-256 biner handshake_v2.py, handshake_cli.py, lalu test_handshake_v2.py).

| Command atau pemeriksaan aktual | Hasil dan bukti |
|---|---|
| `python -B -m unittest discover -s tests -p test_engine_v2.py -v` | PASS 18/18 saat preflight. Agreement KEM, HKDF-SHA256, AEAD, nonce, dan komposisi lokal terverifikasi. |
| `python -B -m unittest discover -s tests -p test_handshake_v2.py -v` | PASS 13/13. Kelima frame, keempat proof dan pemetaan kunci arah cocok dengan perhitungan pembanding dalam tes. CLI server dan client berakhir dengan exit 0 dan session ID sama. |
| Uji negatif dalam suite handshake | PASS. Wrong PSK, proof PSK client rusak, perubahan transcript dan Finished, replay SERVER_HELLO, ketidakcocokan secret, suite/version/role/urutan salah, panjang tidak valid, dan EOF terpotong menimbulkan penolakan pada endpoint pemeriksa. Uji split read dan idle memeriksa deadline total. Kunci sesi baru berbeda dan akses melalui sesi tertutup ditolak. |
| `python -B -m unittest discover -s tests -v` | PASS 45/45, tanpa skip. Termasuk seluruh Stage 03 dan tiga kombinasi CLI chat lama pada TCP loopback. |
| `python -B smoke_test.py`, `python -B -m protocol.handshake_cli --help`, pemeriksaan `sys.modules` sesudah `import chat` | PASS. Agreement/dekripsi baseline berhasil, CLI tersedia, chat tetap memakai jalur Stage 02. |

Keputusan: versi 2, suite 1, PSK biner 32 byte, satu deadline default 10 detik, dan CLI khusus satu handshake. Server menerbitkan sesi sesudah mengirim proof terakhir. Client baru menerbitkannya setelah verifikasi. Sesi memberikan kunci trafik dan menutup socket saat keluar dari context manager. [Kontrak wire, batas konfirmasi, dan panduan](docs/secure_handshake.md)

Hasil ini mendukung evaluasi autentikasi dan pembentukan sesi aman pada level prototipe. Pengiriman DATA/ACK v2, pengujian gangguan jaringan, recovery, serta validasi Stage 04 di Ubuntu dan Debian belum dijalankan. Stage 05 menunggu otorisasi pengguna.

## 26 November 2026 — Stage 03, engine lokal

**Status: kriteria Stage 03 lulus pada Windows lokal.** Host menggunakan CPython 3.11.9, pqcrypto 1.0.0 dan cryptography 49.0.0 dari direktori dependency sementara Stage 02 melalui PYTHONPATH. Branch master belum memiliki commit. Identitas source uji adalah SHA-256 `aa1580e34010ff576ebf5fdd9bec1b4c09eb108e42e0c0de5924571a71086d5b`, dihitung atas gabungan digest SHA-256 biner file Python di crypto_engine/v2 menurut nama terurut, diikuti digest tests/test_engine_v2.py.

Engine berada di namespace tersendiri sehingga kedua endpoint tetap mengimpor implementasi legacy. Keputusan lokal mencakup salt dari dua random 32 byte, empat label HKDF, counter sequence milik caller, dan tracker nonce terkunci dengan batas 65.536 record per directional key. Kontrak input/output dan penanganan error tersedia di [dokumentasi engine](docs/crypto_engine.md).

| Pemeriksaan aktual | Hasil |
|---|---|
| Sebelum perubahan, `python -B -m unittest discover -s tests -v` | PASS, 14/14 tes Stage 02. Hash arsip asli cocok dengan log baseline. |
| Probe `inspect.signature`, ukuran hasil ML-KEM dan penolakan bentuk kunci malformed | PASS. keygen(), encaps(pk_bytes), decaps(sk_bytes, ct_bytes). Ukuran 1184/2400/1088/32. Public key nonkanonis dan private key dengan hash internal rusak ditolak library. |
| `python -B -m unittest discover -s tests -p test_engine_v2.py -q` | PASS, 18/18. Agreement dan implicit rejection, validasi input/output, vektor RFC 5869, sensitivitas konteks dan label, encoding AAD, batas ukuran, AES-GCM, tampering, collision, penggunaan konkuren, kuota dan reservasi setelah error diuji. Uji komposisi mencakup dua arah dalam memori. |
| Sesudah perubahan, `python -B -m unittest discover -s tests -v` | PASS, 32/32 tanpa skip. Termasuk tiga pasangan CLI loopback dari Stage 02. |
| `python -B smoke_test.py` dan pemeriksaan `sys.modules` sesudah `import chat` | PASS. Agreement serta dekripsi baseline berhasil. Import entry point chat tidak memuat crypto_engine.v2. |

Pengujian ini mencakup primitive kriptografi dan komposisi lokal. Autentikasi identitas, proof key confirmation, pembentukan transcript oleh handshake, serta pengiriman frame baru menunggu integrasi Stage 04–05. Runtime guest Stage 03 berstatus NOT RUN. Tidak ada hasil sertifikasi atau pengukuran resilience dari tahap ini.

## 26 November 2026 — Stage 02, refactor dan regresi

Pengguna melaporkan Stage 00 dan Stage 01 telah divalidasi dan memberi instruksi untuk Stage 02. Catatan pemeriksaan sebelumnya disimpan sebagai riwayat. Hasil guest dari pengguna belum disalin ke log ini. Branch lokal masih belum memiliki commit. Status Stage 02 adalah **kriteria teknis terverifikasi di Windows**, menunggu validasi pengguna. Runtime Stage 02 pada kedua guest berstatus **NOT RUN**.

### Perubahan dan keputusan

- `chat.py` mempertahankan perintah dengan submode server/client dan mengekspor ulang fungsi lama untuk framing, derivasi kunci, dan sesi. `client.py` dan `server.py` juga dapat dijalankan langsung. `config.py` menyatukan opsi endpoint dan batas body.
- `protocol/transport.py` memindahkan framing asli. `protocol/handshake.py` menangani pertukaran dua frame serta fingerprint. `protocol/session.py` menjalankan I/O chat, dua counter, receiver thread, dan shutdown.
- `crypto_engine/kem.py` meneruskan API ML-KEM-768 yang sama. `crypto_engine/kdf.py` memindahkan HKDF-SHA512 dan pembagian kunci. `crypto_engine/aead.py` menyatukan pembentukan nonce dan AAD berdasarkan arah serta counter.
- Baseline dicek sebelum pengeditan. Semua file awal identik dengan ZIP. Sesudah refactor, `smoke_test.py` dan `requirements.txt` masih identik dengan ZIP. Arsip asli tetap dapat dibaca dan kedua uji campuran mengekstrak `chat.py` asli serta memverifikasi SHA-256 sebelum menjalankannya.
- Dokumentasi menjelaskan alur dan perintah di [README](README.md) serta [arsitektur dan diagram Mermaid](docs/architecture.md).

### Pemeriksaan aktual Stage 02

Host Windows memilih CPython 3.11.9 untuk tes runtime. Dependency yang telah tercantum di requirements dipasang setelah persetujuan ke direktori sementara `%TEMP%\hpqc-stage02-deps-20261126` dengan `python.exe -B -m pip --disable-pip-version-check install --no-cache-dir --only-binary=:all: --target <direktori> -r requirements.txt`. `PYTHONPATH` disetel ke direktori tersebut pada shell uji. Versi yang dipakai ialah pqcrypto 1.0.0, cryptography 49.0.0, dan psutil 7.2.2.

| Pemeriksaan | Status | Bukti |
|---|---|---|
| `python.exe -B smoke_test.py` | PASS | Exit 0, ML-KEM shared secret cocok dan AES-GCM dekripsi benar. |
| Probe API dengan `inspect.signature` dan KEM round-trip | PASS | `keygen()`, `encaps(pk_bytes)`, `decaps(sk_bytes, ct_bytes)`. Ukuran 1184/2400/1088/32 byte dan shared secret cocok. |
| `python.exe -B -m unittest discover -s tests -v` | PASS | 14 tes lulus. Import modul, framing dan batas/EOF, HKDF, identitas hasil AES-GCM untuk nonce/AAD asal, dan penolakan tag saat arah atau counter salah. Tiga pasangan aplikasi bertukar empat pesan UTF-8 melalui TCP loopback dan berakhir dengan exit 0. Pasangannya adalah aplikasi modular, client asli ke server modular, serta client modular ke server asli. |
| `python.exe -B -m unittest discover -s tests -p test_interoperability.py -q`, 10 pengulangan | PASS | 30 dari 30 uji. Pada run pertama sebelum sinkronisasi test harness, satu assertion menangkap baris penerima parsial karena output thread terminal dapat terseling. Harness kini menunggu prompt kesiapan dan keluaran pengirim sebelum memeriksa terminal penerima. |
| `python.exe -B` dengan `compile()` dalam memori, Python 3.11.9 dan 3.15.0 | PASS | Masing-masing memeriksa 15 file Python. |
| `python.exe -B chat.py --help` dan opsi `--help` pada `client.py` serta `server.py` | PASS | Ketiganya exit 0. Opsi mode lama dan opsi host/port tersedia. |
| `zipfile`, `hashlib`, pemeriksaan tautan lokal dan blok kode | PASS | Hash ZIP, integritas arsip, dan dua file asli yang dipertahankan cocok. Tautan lokal dan pembatas blok kode tersedia. |
| Runtime di Ubuntu dan Debian | NOT RUN | Pengujian Stage 02 di guest dapat dijalankan dengan perintah pada README. |

### Known issues

Fingerprint memerlukan perbandingan manual. Pesan console dari thread kirim dan terima dapat terseling, dan prompt input bisa tetap menunggu setelah peer terputus. Server melayani satu koneksi per proses. Status pengiriman lokal belum membuktikan penerimaan aplikasi. Validasi pengguna atas Stage 02 adalah batas sebelum Stage 03.

## 26 November 2026 — baseline sebelum refactor

| Stage | Status | Bukti dan kriteria terbuka |
|---|---|---|
| 00 | Parsial | Inventaris host, audit, arsip empat file, dan uji restore selesai. Branch master belum memiliki commit. Pencatatan baseline sebagai commit menunggu persetujuan pengguna. |
| 01 | Parsial | Pemeriksaan sintaks lulus pada dua interpreter Windows. Runtime Windows BLOCKED. Semua pengujian di dalam Ubuntu dan Debian, delivery dua arah, serta capture masih NOT RUN. |
| 02–11 | Belum dimulai | Kriteria tahap berikutnya ada di [ROADMAP.md](ROADMAP.md). |

### Baseline yang dapat dipulihkan

Arsip tersimpan di `../hpqc_demo_baselines/prototype-original-20261126.zip`, relatif terhadap root proyek. Arsip memuat empat file asli di root ZIP. SHA-256 arsip adalah `4C96CD9F4462B5B1A1F1350C4B1FD4EA572C80343F76997B41625E19B381A981`. Lokasinya terpisah dari working tree, pada disk host yang sama.

| File | Byte | SHA-256 sumber, sama dengan salinan hasil restore |
|---|---:|---|
| chat.py | 5204 | `40AB14EC37AEF318DE299603EFA1511D86AE1D1C342A36347861CF99F8B792A1` |
| smoke_test.py | 931 | `A9BE8AACDEE545FC7E88542DEBAF77656E3D6375D9C3EEF58A0CDBE396BCF2ED` |
| requirements.txt | 50 | `034CF5B60C613C752EA7D90856E3537D3866D58DD1A526F8E4D78D4E0034CBA5` |
| README.md | 1319 | `8B772873858E9333FDB97CD79325D8720813DBE1F9CD9EFBCE1662431D524B9D` |

Untuk memulihkan ke direktori baru dari root proyek, cocokkan dahulu hash arsip. Bandingkan keluaran akhir dengan keempat hash pada tabel.

```powershell
$zip = '..\hpqc_demo_baselines\prototype-original-20261126.zip'
$expected = '4C96CD9F4462B5B1A1F1350C4B1FD4EA572C80343F76997B41625E19B381A981'
if ((Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash -ne $expected) { throw 'Hash arsip berbeda' }
$restoreDir = Join-Path ([IO.Path]::GetTempPath()) ('hpqc-restore-' + [guid]::NewGuid().ToString('N'))
Expand-Archive -LiteralPath $zip -DestinationPath $restoreDir -ErrorAction Stop
Get-ChildItem -File -LiteralPath $restoreDir | Get-FileHash -Algorithm SHA256 | Format-List Path,Hash
```

### Pemeriksaan aktual

| Pemeriksaan / command | Status | Hasil |
|---|---|---|
| `git --no-optional-locks status --short --branch --untracked-files=all`, `git ls-files --stage`, `git remote`, `git --version` | PASS | Kondisi awal: empat file asli dan dua cache .pyc untracked, index kosong, tanpa remote. Git 2.56.0.windows.2. |
| `Get-ChildItem -Force`, `rg --files --hidden` dengan .git dikecualikan, `Get-Content -Raw` dan `Get-FileHash -Algorithm SHA256` pada empat file | PASS | Isi dibaca kembali. Seluruh hash sama dengan preflight. |
| `Get-Command -All`, direktori interpreter, variabel venv, registry Windows, versi PowerShell dan executable VirtualBox, XML VirtualBox.xml dan dua file .vbox | PASS | Dua interpreter dasar ditemukan. Kedua adapter guest terkonfigurasi pada PQC-LAB. Rincian di [inventaris](docs/environment_inventory.md). |
| `Compress-Archive -LiteralPath` untuk empat file, `Expand-Archive` ke direktori sementara baru, perbandingan daftar file dan `Get-FileHash` setiap file | PASS | Restore ke `%TEMP%\hpqc-restore-8604efe6cd624c93ad74c817a38ad5ca`; tepat empat nama file, semua SHA-256 cocok. |
| Pada kedua CPython Windows: `python.exe -B -` dengan `compile(Path(file).read_bytes(), file, "exec")` | PASS | chat.py dan smoke_test.py lulus pada 3.11.9 dan 3.15.0. Empat pemeriksaan, di memori. |
| `importlib.metadata.version()` dan `import_module()` pada masing-masing interpreter | FAIL untuk import dependency runtime | Keduanya menghasilkan `No module named 'pqcrypto'` serta `No module named 'cryptography'`. Import psutil PASS pada 3.11.9 (7.2.2); pada 3.15.0 muncul `No module named 'psutil'`. |
| Windows: smoke_test.py, import fungsi KEM aktual, dan chat loopback | BLOCKED | Probe modul gagal sebelum fungsi KEM dapat diperiksa. Smoke test dan proses chat tidak diluncurkan. |
| Ubuntu-PQC / Debian-PQC: inventaris dalam guest, import API, ukuran KEM, agreement, smoke, chat, capture | NOT RUN | Tidak ada koneksi ke VM. Belum ada exit code, transkrip penerima, atau pcap dari guest. [Prosedur manual](docs/testing_guide.md) |
| `git check-ignore -v/-q`, status Git dan index | PASS | Sembilan contoh cache, venv, credential, dan bukti privat diabaikan. Enam contoh termasuk source dan ringkasan CSV tetap dapat dilacak. Index kosong. |
| Pemeriksaan akhir Python 3.11 dengan `zipfile`, `hashlib`, dan `pathlib` | PASS | SHA-256 arsip cocok dengan log. Empat file aktif identik byte demi byte dengan isi ZIP. Tautan file lokal dan pagar blok kode diperiksa di lima dokumen, dan roadmap memuat tepat Stage 00–11 berurutan. |

### Keputusan teknis dan known issues

- Pertahankan `chat.py`, `smoke_test.py`, `requirements.txt`, dan README asli sebagai pembanding. Rencana commit awal setelah persetujuan adalah memilih empat file baseline secara eksplisit, memeriksa staged diff, dan mencatat ID commit. Dokumen baru dipisahkan dari snapshot asli.
- Kode meminta `keygen()`, `encaps(public)`, `decaps(private, ct)` dari `pqcrypto.kem.ml_kem_768`. API sesuai dengan dokumentasi rilis yang dipatok. Bukti eksekusi lokal dan guest belum tersedia. [pqcrypto 1.0.0](https://pypi.org/project/pqcrypto/1.0.0/)
- Chat memakai ephemeral ML-KEM-768, HKDF-SHA512, dua directional AES-256-GCM keys, serta nonce dan AAD berbasis counter. Fingerprint hanya ditampilkan. Aplikasi belum memverifikasi identitas, mengonfirmasi shared secret, atau memberikan application ACK.
- Prefix 4 byte membatasi body sampai 1.048.576 byte. Plaintext chat maksimum 1.048.560 byte setelah memperhitungkan tag 16 byte. Satu frame dapat melintasi batas segmen TCP.
- Server menerima satu koneksi. Client menonaktifkan timeout sesudah TCP connect. Sesudah peer menutup socket, thread utama dapat tetap menunggu input terminal. Belum ada reconnect atau metrik recovery.
- Smoke test mengukur round-trip kriptografi dalam satu proses. Waktu satu kali operasi atau tampilan “handshake selesai” belum cukup untuk menyimpulkan performa jaringan, mutual authentication, atau resilience.

### Bukti yang ditunggu

Catat persetujuan dan ID commit baseline bila tersedia. Untuk masing-masing guest, isi identitas environment dan tambahkan bukti sesuai [panduan Stage 01](docs/testing_guide.md). Catat ukuran frame dari capture, kedua arah penerimaan, dan perilaku penutupan. Tahan status selesai sampai bukti tersebut tersedia.
