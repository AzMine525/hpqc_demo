# Log pengembangan dan verifikasi HPQC

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
