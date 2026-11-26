# Stage 09 — Pemulihan pengiriman HPQC

Profil Stage 09 mengirim pesan biner sampai 1 MiB ke inbox pasangan endpoint. Satu ID aplikasi 16 byte mewakili satu pengiriman logis selama semua retry. Setiap koneksi memakai handshake PSK dan key confirmation baru dengan suite yang dipilih secara lokal. Endpoint menjalankan profil ini secara eksplisit melalui `protocol.resilience_cli`. Gunakan PSK khusus per pasangan dan profil, serta satu database inbox untuk pasangan tersebut. [Handshake v2](secure_handshake.md) · [DATA dan ACK v2](secure_data.md)

## Alur pengiriman dan pemulihan

1. Client memulai TCP dan handshake dengan timeout. Setelah `secure_ready`, client mengirim kontrol `HPQ9 || 0x01 || logical_id` sebagai payload DATA v2, lalu mengirim payload pengguna sebagai DATA tersendiri. Masing-masing memakai ID record baru dan memperoleh ACK v2. Pemisahan ini menyediakan kapasitas penuh 1 MiB untuk payload pengguna.
2. Server menerima data terautentikasi dan melakukan transaksi SQLite pada tabel `inbox(message_id, payload)`. ID baru menghasilkan satu baris. ID lama dengan byte identik menghasilkan event `duplicate`. ID yang sama dengan isi berbeda ditolak. Sesudah commit, server mengirim receipt `HPQ9 || 0x02 || logical_id` melalui DATA v2. Client melaporkan `delivered` setelah memverifikasi receipt untuk ID yang sedang ditunggu. ACK v2 sendiri hanya menunjukkan penerimaan record di memori.
3. Saat jeda antar-pengiriman, client menjadwalkan PING `HPQ9 || 0x03 || challenge` dengan challenge acak 16 byte dan memeriksa PONG bertipe `0x04` yang menggemakannya. API juga menyediakan `heartbeat()` dan `wait(duration, interval)`. Server menutup sesi idle setelah `--idle-timeout`. Atur interval heartbeat lebih pendek dari batas idle server dengan ruang untuk RTT.
4. EOF, error socket dan handshake timeout menghentikan channel lama. Client mencoba kembali operasi dengan ID yang sama, backoff eksponensial terbatas, TCP baru, dan handshake lengkap. Sesi baru menghasilkan kunci, session ID, sequence, dan riwayat nonce baru. Frame lama tidak dikirim ulang. Kesalahan proof, suite atau record yang terdeteksi lokal menghentikan operasi. Jika peer hanya menutup socket, client melihat EOF dan menerapkan batas retry.
5. Opsi `--retries N` mengizinkan satu percobaan awal dan paling banyak N retry per operasi. Jeda pertama memakai `--backoff`, lalu dua kali lipat sampai `--backoff-cap`. Batas I/O transaksi menggunakan satu deadline monotonic yang diperiksa sepanjang pembacaan parsial dan penulisan. Connect dan handshake masing-masing memiliki batas waktu tersendiri. Saat retry habis, hasil akhir pengiriman dapat belum diketahui client. Pakai ID dari event `attempt_started` dengan payload yang sama untuk melanjutkan.

Inbox mendefinisikan delivery sebagai commit baris. Restart server dapat memakai kembali database yang sama. Eksekusi efek eksternal sesudah commit, beberapa client serentak, pemulihan database yang hilang dan penyimpanan outbox client di luar umur proses berada di luar jaminan ini. Database menyimpan plaintext setelah dekripsi. Gunakan direktori lab privat untuk data sintetis. Retensi ID harus mencakup periode retry dan pengiriman ulang operator.

## Menjalankan pada Windows, Ubuntu, atau Debian

Gunakan root proyek dan environment dengan dependency proyek. Buat direktori `private-data` lalu siapkan berkas PSK acak 32 byte di kedua endpoint melalui prosedur provisioning lab. Contoh ini mengasumsikan `private-data/peer.psk` tersedia. Pada Windows gunakan executable Python venv atau interpreter di inventaris. Pada Linux dapat memakai `python3`. [Provisioning PSK biner](secure_handshake.md)

Jalankan server di terminal pertama. Ia mempertahankan inbox dan menerima koneksi baru secara berurutan sampai Ctrl+C.

```text
python -B -m protocol.resilience_cli server --host 127.0.0.1 --port 5050 --psk-file private-data/peer.psk --inbox private-data/peer.sqlite --suite ml-kem-768 --timeout 3 --idle-timeout 15
```

Di terminal kedua jalankan client. Untuk VM gunakan IP interface data server pada kedua perintah. `--input FILE` dapat menggantikan `--text`. Untuk mengulang satu pesan yang hasilnya ambigu, tambahkan `--message-id HEX32` dan gunakan `--count 1`.

```text
python -B -m protocol.resilience_cli client --host 127.0.0.1 --port 5050 --psk-file private-data/peer.psk --suite ml-kem-768 --text "uji pemulihan" --count 45 --interval 1 --heartbeat 0.3 --timeout 3 --retries 8 --backoff 0.2 --backoff-cap 2
```

Untuk uji lokal ulang, gunakan file output baru di direktori yang sudah ada.

```text
python -B -m benchmark.bench_resilience --output results/stage09/ulangan.json
python -B -m unittest discover -s tests -p test_resilience.py -v
python -B -m unittest discover -s tests -v
python -B smoke_test.py
```

## Bukti dan definisi metrik

Eksperimen loopback memakai tiga pesan sintetis 1 KiB dan tiga heartbeat per skenario. Pada skenario outage, server menghentikan sesi setelah commit pesan kedua, sebelum receipt terkirim. Untuk jendela 200 ms aplikasi menutup koneksi baru yang diterima listener. Run mencocokkan seluruh isi database dengan tiga pesan asal. `at_ns` dan `since_detection_ns` berasal dari `perf_counter_ns()`. Pada dua host, hitung selisih waktu di client saja. [Event mentah dan identitas source](../results/stage09/loopback.json)

| Metrik | Definisi | Normal | Outage layanan |
|---|---|---:|---:|
| Delivery terkonfirmasi | Receipt valid dibagi jumlah pesan logis | 3/3 | 3/3 |
| Inbox dan duplikat | Baris unik setelah run, lalu jumlah kiriman ulang yang dikenali | 3 dan 0 | 3 dan 1 |
| Receipt selama / sesudah outage | Receipt yang client verifikasi dalam / setelah jendela | — | 0 / 2 |
| TCP pulih | Dari deteksi gangguan pertama ke connect TCP pertama yang berhasil | — | 41,514 ms |
| TCP untuk sesi terkonfirmasi | Dari deteksi ke connect TCP pada percobaan yang kemudian lolos handshake | — | 266,167 ms |
| Sesi aman pulih | Dari deteksi ke akhir handshake dan pembentukan channel | — | 270,239 ms |
| Delivery pulih | Dari deteksi ke receipt sah pertama | — | 272,833 ms |
| Timeout / percobaan | Timeout client dibagi jumlah percobaan DATA dan heartbeat, termasuk retry | 0/6 | 0/9 |

Run outage mencatat tiga interupsi transport. Satu receipt tiba sebelum gangguan. Listener TCP masih aktif selama outage layanan sehingga connect dapat sukses sebelum aplikasi kembali siap. Tes terpisah memverifikasi timeout pada peer yang diam, penolakan PSK salah, batas retry, dan deduplikasi setelah database dibuka kembali. Angka tabel adalah satu observasi Windows ML-KEM-768 per skenario. [Transkrip regresi](../results/stage09/test-results.txt)

## Panduan manual Linux tc netem dan rollback

Status pengujian guest **NOT RUN**. Langkah berikut untuk operator setelah ada izin eksplisit untuk interface data, arah, profil, dan durasi. Gunakan konsol VirtualBox atau jalur manajemen terpisah yang telah dicoba. Periksa akses konsol dan jalur balik SSH sebelum, selama, dan setelah uji. Pada pemeriksaan XML host, Ubuntu-PQC dan Debian-PQC masing-masing menampilkan satu NIC aktif di PQC-LAB. Verifikasi rute aktif di dalam guest pada hari pengujian.

1. Dari konsol guest catat `ip -br addr`, `ip route get <IP-peer-data>`, dan bila memakai SSH, `ip route get <IP-pengelola>`. Catat interface fisik/virtual yang dipilih dan konfirmasikan akses konsol independen. Jalankan baseline dua terminal tanpa qdisc tambahan dan simpan event JSON Lines pada kedua endpoint. Jalankan satu profil per percobaan. Contoh membatasi perubahan pada egress interface data khusus yang hanya membawa trafik eksperimen.
2. Isi variabel shell `LAB_IF` dan `DATA_PEER` dari observasi. Pada sesi SSH, `MGMT_PEER` harus memuat IP pengelola. Periksa `tc qdisc show dev "$LAB_IF"`, `tc class show dev "$LAB_IF"`, serta `tc filter show dev "$LAB_IF" root`. Contoh rollback berikut berlaku untuk root default kernel handle `0:` tunggal, tanpa class/filter kustom. Untuk konfigurasi lain siapkan dan verifikasi prosedur pemulihan yang sesuai konfigurasi awal. Simpan output baseline beserta identitas interface di berkas bukti lab.
3. Mulai server dan client menggunakan contoh di atas dengan IP lab dan file log baru. Pada terminal kedua di guest pengirim, setelah delivery awal, jalankan blok Bash berikut dari konsol dengan izin pengelolaan jaringan. Tentukan `PROFILE` dari tabel, lalu pilih durasi. Jalankan blok sebagai satu kesatuan. Ia hanya menghapus handle milik percobaan ini dan membandingkan konfigurasi sesudah rollback dengan baseline.

| Profil | Nilai `PROFILE` | Target |
|---|---|---|
| Normal | tanpa menjalankan blok | Baseline tanpa impairment |
| Loss | `loss5`, `loss10`, `loss20` | 5%, 10%, 20% pada egress |
| Delay | `delay50`, `delay100`, `delay200` | 50, 100, 200 ms pada egress |
| Delay dengan jitter | `jitter10`, `jitter20` | 50 ms dengan variasi 10 atau 20 ms |
| Outage sementara | `outage` | 100% loss egress selama lima detik, lalu rollback |

```bash
(
  set -euo pipefail
  : "${LAB_IF:?isi interface data}" "${DATA_PEER:?isi IP data peer}" "${PROFILE:?pilih profil}"
  route_dev() { ip -4 route get "$1" | awk '{for(i=1;i<NF;i++) if($i=="dev"){print $(i+1);exit}}'; }
  test "$LAB_IF" != lo
  test "$(route_dev "$DATA_PEER")" = "$LAB_IF"
  if [ -n "${SSH_CONNECTION:-}" ]; then
    test "${MGMT_PEER:?isi IP pengelola}" = "${SSH_CONNECTION%% *}"
  fi
  if [ -n "${MGMT_PEER:-}" ]; then
    management=$(route_dev "$MGMT_PEER")
    test -n "$management" && test "$management" != "$LAB_IF" || exit 1
  fi
  before=$(tc qdisc show dev "$LAB_IF")
  test "$(echo "$before" | wc -l)" -eq 1
  echo "$before" | grep -Eq '^qdisc [^ ]+ 0: root'
  classes=$(tc class show dev "$LAB_IF")
  filters=$(tc filter show dev "$LAB_IF" root)
  test -z "$classes" && test -z "$filters" || exit 1
  seconds=12
  case "$PROFILE" in
    loss5|loss10|loss20) set -- loss "${PROFILE#loss}%";;
    delay50|delay100|delay200) set -- delay "${PROFILE#delay}ms";;
    jitter10|jitter20) set -- delay 50ms "${PROFILE#jitter}ms";;
    outage) set -- loss 100%; seconds=5;;
    *) exit 2;;
  esac
  rollback() {
    tc qdisc show dev "$LAB_IF" | grep -Eq '^qdisc netem 709: root' || return 1
    tc qdisc del dev "$LAB_IF" root handle 709: || return 1
    after=$(tc qdisc show dev "$LAB_IF")
    echo "$after"
    test "$after" = "$before"
  }
  tc qdisc add dev "$LAB_IF" root handle 709: netem "$@"
  trap 'rollback || { echo "Rollback perlu verifikasi konsol" >&2; exit 1; }' EXIT
  trap 'exit 1' HUP INT TERM
  tc -s qdisc show dev "$LAB_IF"
  sleep "$seconds"
  tc -s qdisc show dev "$LAB_IF"
)
```

4. Jika shell terputus, gunakan konsol dan periksa handle aktual. Jika masih ada `netem 709: root` milik percobaan, jalankan `tc qdisc del dev "$LAB_IF" root handle 709:` dan cocokkan qdisc, class, filter, serta rute dengan baseline tersimpan. Bila pemeriksaan berbeda, catat kondisi dan pulihkan baseline sebelum profil berikutnya. Konfirmasi akses pengelola dan kirim satu pesan baru sampai ada receipt serta baris inbox yang cocok.
5. Catat waktu mulai/akhir impairment, suite, parameter retry, event client/server, dan statistik `tc -s`. Pada client rekam `ss -ti` untuk koneksi terkait selama pengujian bila tersedia. Bedakan drop pada qdisc, retransmisi TCP, timeout aplikasi, receipt, serta komit unik. Bila batas retry habis, pertahankan log dan kirim ulang dengan ID yang sama setelah pemulihan. Delay pada satu egress bekerja satu arah. Untuk arah sebaliknya lakukan run tersendiri dan catat endpoint tempat qdisc dipasang. [Manual iproute2 untuk tc-netem](https://man7.org/linux/man-pages/man8/tc-netem.8.html)
